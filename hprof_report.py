#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hprof_report.py - Java 힙 덤프(HPROF) 분석 → HTML 보고서 생성기

Python 표준 라이브러리만 사용한다 (Python 3.7+, 외부 패키지 설치 불필요).

사용 예
    python3 hprof_report.py heap.hprof                     # heap_report.html 생성
    python3 hprof_report.py heap.hprof -o out.html --top 50
    python3 hprof_report.py heap.hprof.gz                  # jcmd ... -gz=1 압축 덤프도 지원
    python3 hprof_report.py heap.hprof --json result.json  # 분석 결과를 JSON으로도 저장
    python3 hprof_report.py huge.hprof --fast              # dominator/retained 계산 생략 (대용량용)

힙 덤프 받기
    jcmd <pid> GC.heap_dump /path/heap.hprof        # live 객체만 (Full GC 후 덤프)
    jcmd <pid> GC.heap_dump -all /path/heap.hprof   # unreachable 객체 포함
    java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/path ...

보고서 내용
    요약 / 누수 의심(Leak Suspects) / Dominator Tree / 클래스 히스토그램 / 컬렉션 /
    중복 문자열 / 스레드(스택 + 지역변수) / 클래스로더 / GC Root / unreachable 객체

계산 방식
    * HPROF에는 객체의 실제 메모리 크기가 없으므로 shallow 크기는 HotSpot 레이아웃
      (객체 헤더, 참조 크기, 8바이트 정렬)으로 추정한다. Compressed OOPs 여부는 객체 주소
      간격으로 자동 판별한다 (--oops 로 지정 가능).
    * Retained 크기는 객체 그래프의 dominator tree(Lengauer-Tarjan)로 계산한다. weak/soft
      참조도 강참조로 취급한다 (Eclipse MAT 기본 동작과 동일). 단, GC Root 경로를 찾을 때는
      weak/soft 참조(Reference.referent)를 제외한다.
    * 메모리: 분석 중 객체 1개당 대략 300~400바이트를 사용한다. 객체가 수천만 개면 --fast 를
      쓰거나 메모리가 넉넉한 장비에서 실행한다.
"""

import argparse
import gzip
import hashlib
import html
import json
import mmap
import os
import shutil
import struct
import sys
import tempfile
import time
from array import array
from collections import Counter, defaultdict
from datetime import datetime
from itertools import accumulate, islice

__version__ = "1.0.0"

# ---------------------------------------------------------------------------------------
# HPROF 상수
# ---------------------------------------------------------------------------------------
T_OBJECT = 2
PRIM_SIZE = {4: 1, 5: 2, 6: 4, 7: 8, 8: 1, 9: 2, 10: 4, 11: 8}
PRIM_NAME = {4: "boolean", 5: "char", 6: "float", 7: "double", 8: "byte", 9: "short", 10: "int", 11: "long"}
PRIM_FMT = {4: "B", 5: "H", 6: "f", 7: "d", 8: "b", 9: "h", 10: "i", 11: "q"}
DESC_PRIM = {"Z": "boolean", "C": "char", "F": "float", "D": "double", "B": "byte", "S": "short", "I": "int", "J": "long"}

K_INSTANCE, K_OBJARRAY, K_PRIMARRAY, K_CLASS = 0, 1, 2, 3

ROOT_NAMES = {
    0xFF: "Unknown", 0x01: "JNI Global", 0x02: "JNI Local", 0x03: "Java Local", 0x04: "Native Stack",
    0x05: "System Class", 0x06: "Thread Block", 0x07: "Busy Monitor", 0x08: "Thread",
    0x89: "Interned String", 0x8A: "Finalizing", 0x8B: "Debugger", 0x8C: "Reference Cleanup",
    0x8D: "VM Internal", 0x8E: "JNI Monitor",
}

# 컬렉션 크기를 읽는 방법: 클래스명 -> (요소 수 필드, 용량(배열) 필드)
COLLECTION_SPECS = {
    "java.util.HashMap": ("size", "table"),
    "java.util.Hashtable": ("count", "table"),
    "java.util.WeakHashMap": ("size", "table"),
    "java.util.IdentityHashMap": ("size", "table"),
    "java.util.concurrent.ConcurrentHashMap": ("baseCount", "table"),
    "java.util.ArrayList": ("size", "elementData"),
    "java.util.Vector": ("elementCount", "elementData"),
    "java.util.LinkedList": ("size", None),
    "java.util.TreeMap": ("size", None),
    "java.util.PriorityQueue": ("size", "queue"),
    "java.util.concurrent.ArrayBlockingQueue": ("count", "items"),
    "java.util.concurrent.LinkedBlockingDeque": ("count", None),
    "java.util.concurrent.LinkedBlockingQueue": ("count.value", None),
    "java.util.concurrent.CopyOnWriteArrayList": ("array.length", "array"),
    "java.util.ArrayDeque": ("<deque>", "elements"),
    "java.util.HashSet": ("map.size", "map.table"),
    "java.util.TreeSet": ("m.size", None),
}

BOXED = {"java.lang.Integer", "java.lang.Long", "java.lang.Short", "java.lang.Byte", "java.lang.Character",
         "java.lang.Boolean", "java.lang.Float", "java.lang.Double"}


def java_name(raw):
    """'java/lang/String' -> 'java.lang.String', '[[Ljava/lang/Object;' -> 'java.lang.Object[][]'"""
    if not raw.startswith("["):
        return raw.replace("/", ".")
    dims = len(raw) - len(raw.lstrip("["))
    rest = raw[dims:]
    if rest.startswith("L") and rest.endswith(";"):
        base = rest[1:-1].replace("/", ".")
    else:
        base = DESC_PRIM.get(rest, rest.replace("/", "."))
    return base + "[]" * dims


def fmt_bytes(n):
    if n is None:
        return "-"
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(v) < 1024 or unit == "TB":
            return "%d B" % v if unit == "B" else "%.1f %s" % (v, unit)
        v /= 1024.0
    return str(n)


def thread_state(status):
    """JVMTI thread status 비트 → Thread.State 이름 (sun.misc.VM.toThreadState 와 동일 규칙)"""
    if status is None:
        return "?"
    if status & 0x0004:
        return "RUNNABLE"
    if status & 0x0400:
        return "BLOCKED"
    if status & 0x0010:
        return "WAITING"
    if status & 0x0020:
        return "TIMED_WAITING"
    if status & 0x0002:
        return "TERMINATED"
    if status & 0x0001 == 0:
        return "NEW"
    return "RUNNABLE"


class Logger(object):
    def __init__(self, quiet=False):
        self.quiet = quiet
        self.t0 = time.time()

    def __call__(self, msg):
        if not self.quiet:
            sys.stderr.write("[%7.1fs] %s\n" % (time.time() - self.t0, msg))
            sys.stderr.flush()


class Layout(object):
    """JVM 객체 레이아웃 (shallow 크기 추정용)"""

    MODES = {
        # mode: (object header, reference size, array header)
        "compressed": (12, 4, 16),
        "uncompressed": (16, 8, 24),
        "32bit": (8, 4, 12),
    }

    def __init__(self, mode):
        self.mode = mode
        self.hdr, self.ref, self.arr = self.MODES[mode]


class ClassInfo(object):
    __slots__ = ("ci", "cid", "name", "super_id", "loader_id", "signers_id", "pd_id", "inst_size",
                 "statics", "fields", "cp_refs", "sup", "field_map", "ref_fields", "ref_struct",
                 "n_refs", "prim_bytes", "elem_size", "node", "is_reference", "synthetic", "is_array")

    def __init__(self, ci, cid, name=None):
        self.ci = ci
        self.cid = cid
        self.name = name
        self.super_id = self.loader_id = self.signers_id = self.pd_id = 0
        self.inst_size = 0
        self.statics = []      # [(name, type, value)]
        self.fields = []       # [(name, type)]  이 클래스에 선언된 인스턴스 필드
        self.cp_refs = []
        self.sup = None
        self.field_map = {}    # name -> (type, offset)  (상속 포함, 하위 클래스 우선)
        self.ref_fields = []   # [(name, offset)]
        self.ref_struct = None
        self.n_refs = 0
        self.prim_bytes = 0
        self.elem_size = 0     # 배열 클래스의 원소 크기 (0 = 배열 아님)
        self.node = 0
        self.is_reference = False
        self.synthetic = False
        self.is_array = False


# ---------------------------------------------------------------------------------------
# HPROF 파서 + 객체 그래프
# ---------------------------------------------------------------------------------------
class HeapDump(object):

    def __init__(self, path, log):
        self.path = path
        self.log = log
        self.warnings = []
        self.truncated = False
        self.fh = open(path, "rb")
        self.file_size = os.fstat(self.fh.fileno()).st_size
        if self.file_size == 0:
            raise ValueError("빈 파일입니다: %s" % path)
        self.mm = mmap.mmap(self.fh.fileno(), 0, access=mmap.ACCESS_READ)

        self.strings = {}
        self.class_name_sid = {}     # class id -> name string id
        self.class_serial = {}       # class serial -> class id
        self.frames = {}             # frame id -> (method sid, sig sid, source sid, class serial, line)
        self.traces = {}             # trace serial -> (thread serial, [frame ids])
        self.classes = []
        self.roots = []              # [(tag, object id, thread serial, frame)]
        self.thread_roots = []       # [(thread object id, thread serial, trace serial)]

        # 객체 테이블. 0번 인덱스는 가상 GC Root 노드
        self.obj_id = array("Q", [0])
        self.obj_off = array("Q", [0])   # 데이터 시작 위치 (클래스는 레코드 시작 위치)
        self.obj_kind = bytearray(b"\x00")
        self.obj_cls = array("Q", [0])   # 원본 class id (기본형 배열 = 원소 타입 코드, 클래스 객체 = 1)
        self.obj_len = array("q", [0])   # 인스턴스: 데이터 바이트 수, 배열: 원소 수, 클래스: 클래스 인덱스

    def close(self):
        try:
            self.mm.close()
        except Exception:
            pass
        self.fh.close()

    def warn(self, msg):
        self.warnings.append(msg)
        self.log("경고: " + msg)

    # ------------------------------------------------------------------ parsing
    def parse(self):
        mm = self.mm
        size = len(mm)
        nul = mm.find(b"\x00", 0, 64)
        if nul < 0 or not mm[:nul].startswith(b"JAVA PROFILE"):
            raise ValueError("HPROF 파일이 아닙니다: %s" % self.path)
        self.version = mm[:nul].decode("ascii", "replace")
        pos = nul + 1
        self.idsize, hi, lo = struct.unpack_from(">III", mm, pos)
        if self.idsize not in (4, 8):
            raise ValueError("지원하지 않는 identifier 크기: %d" % self.idsize)
        self.timestamp_ms = (hi << 32) | lo
        pos += 12

        I = self.idsize
        ID = "Q" if I == 8 else "I"
        self.ID = ID
        self.id_array_code = "Q" if I == 8 else ("I" if array("I").itemsize == 4 else "L")
        self.s_id = struct.Struct(">" + ID)
        self.tsize = [0] * 12
        for t, s in PRIM_SIZE.items():
            self.tsize[t] = s
        self.tsize[T_OBJECT] = I
        self.val_struct = dict((t, struct.Struct(">" + f)) for t, f in PRIM_FMT.items())
        self.val_struct[T_OBJECT] = self.s_id

        unpack_from = struct.unpack_from
        s_id = self.s_id
        strings = self.strings
        s_loadclass = struct.Struct(">I%sI%s" % (ID, ID))
        s_frame = struct.Struct(">%s%s%s%sIi" % (ID, ID, ID, ID))
        step = max(size // 20, 1 << 26)
        next_report = step
        n_heap_records = 0

        while pos + 9 <= size:
            tag = mm[pos]
            length = unpack_from(">I", mm, pos + 5)[0]
            body = pos + 9
            end = body + length
            if end > size:
                self.truncated = True
                self.warn("파일이 잘려 있습니다 (레코드 0x%02X @%d). 읽을 수 있는 부분까지만 분석합니다." % (tag, pos))
                end = size
            if tag == 0x0C or tag == 0x1C:
                n_heap_records += 1
                self._parse_heap(body, end)
            elif tag == 0x01:
                strings[s_id.unpack_from(mm, body)[0]] = mm[body + I:end].decode("utf-8", "replace")
            elif tag == 0x02:
                serial, cid, _trace, nsid = s_loadclass.unpack_from(mm, body)
                self.class_name_sid[cid] = nsid
                self.class_serial[serial] = cid
            elif tag == 0x04:
                fid, msid, sigsid, srcsid, cserial, line = s_frame.unpack_from(mm, body)
                self.frames[fid] = (msid, sigsid, srcsid, cserial, line)
            elif tag == 0x05:
                serial, tserial, nframes = unpack_from(">III", mm, body)
                fids = list(struct.unpack_from(">%d%s" % (nframes, ID), mm, body + 12)) if nframes else []
                self.traces[serial] = (tserial, fids)
            pos = end
            if pos >= next_report:
                self.log("  파싱 %3d%%  (객체 %s개)" % (pos * 100 // size, format(len(self.obj_id) - 1, ",")))
                next_report += step
        if n_heap_records == 0:
            raise ValueError("HEAP DUMP 레코드가 없습니다 (힙 덤프가 아닌 HPROF 파일일 수 있음)")

    def _parse_heap(self, pos, end):
        mm = self.mm
        I = self.idsize
        ID = self.ID
        u_inst = struct.Struct(">%s4x%sI" % (ID, ID)).unpack_from
        u_oarr = struct.Struct(">%s4xI%s" % (ID, ID)).unpack_from
        u_parr = struct.Struct(">%s4xIB" % ID).unpack_from
        u_id = self.s_id.unpack_from
        u_id_ii = struct.Struct(">%sIi" % ID).unpack_from
        u_id_i = struct.Struct(">%sI" % ID).unpack_from
        ids_a, off_a, kind_a = self.obj_id.append, self.obj_off.append, self.obj_kind.append
        cls_a, len_a = self.obj_cls.append, self.obj_len.append
        roots_a = self.roots.append
        tsize = self.tsize
        inst_hdr = 2 * I + 8
        oarr_hdr = 2 * I + 8
        parr_hdr = I + 9
        while pos < end:
            tag = mm[pos]
            pos += 1
            if tag == 0x21:  # INSTANCE DUMP
                oid, cid, nbytes = u_inst(mm, pos)
                pos += inst_hdr
                ids_a(oid); off_a(pos); kind_a(0); cls_a(cid); len_a(nbytes)
                pos += nbytes
            elif tag == 0x23:  # PRIMITIVE ARRAY DUMP
                oid, count, et = u_parr(mm, pos)
                pos += parr_hdr
                ids_a(oid); off_a(pos); kind_a(2); cls_a(et); len_a(count)
                pos += count * tsize[et]
            elif tag == 0x22:  # OBJECT ARRAY DUMP
                oid, count, acid = u_oarr(mm, pos)
                pos += oarr_hdr
                ids_a(oid); off_a(pos); kind_a(1); cls_a(acid); len_a(count)
                pos += count * I
            elif tag == 0x20:  # CLASS DUMP
                pos = self._parse_class_dump(pos)
            elif tag in (0x05, 0x07, 0xFF, 0x89, 0x8A, 0x8B, 0x8C, 0x8D):
                roots_a((tag, u_id(mm, pos)[0], -1, -1))
                pos += I
            elif tag == 0x01:  # JNI GLOBAL (object id, global ref id)
                roots_a((tag, u_id(mm, pos)[0], -1, -1))
                pos += 2 * I
            elif tag == 0x02 or tag == 0x03 or tag == 0x8E:  # JNI LOCAL / JAVA FRAME / JNI MONITOR
                oid, ts, fr = u_id_ii(mm, pos)
                roots_a((tag, oid, ts, fr))
                pos += I + 8
            elif tag == 0x04 or tag == 0x06:  # NATIVE STACK / THREAD BLOCK
                oid, ts = u_id_i(mm, pos)
                roots_a((tag, oid, ts, -1))
                pos += I + 4
            elif tag == 0x08:  # THREAD OBJECT
                oid, ts, tr = struct.unpack_from(">%sII" % ID, mm, pos)
                roots_a((tag, oid, ts, -1))
                self.thread_roots.append((oid, ts, tr))
                pos += I + 8
            elif tag == 0x90:  # (Android) UNREACHABLE
                pos += I
            elif tag == 0xC3:  # (Android) PRIMITIVE ARRAY NODATA
                oid, count, et = u_parr(mm, pos)
                ids_a(oid); off_a(0); kind_a(2); cls_a(et); len_a(count)
                pos += parr_hdr
            elif tag == 0xFE:  # (Android) HEAP DUMP INFO
                pos += 4 + I
            else:
                self.warn("알 수 없는 heap 서브레코드 태그 0x%02X @%d - 이 세그먼트의 나머지는 건너뜁니다" % (tag, pos - 1))
                return
        if pos > end and len(self.obj_id) > 1:  # 잘린 파일: 마지막 객체가 불완전하면 버린다
            k = self.obj_kind[-1]
            if k == 0:
                dlen = self.obj_len[-1]
            elif k == 1:
                dlen = self.obj_len[-1] * I
            elif k == 2:
                dlen = self.obj_len[-1] * tsize[self.obj_cls[-1]]
            else:
                dlen = 0
            if k != 3 and self.obj_off[-1] + dlen > end:
                for a in (self.obj_id, self.obj_off, self.obj_cls, self.obj_len):
                    a.pop()
                del self.obj_kind[-1]

    def _parse_class_dump(self, pos):
        mm = self.mm
        I = self.idsize
        rid = self.s_id.unpack_from
        tsize = self.tsize
        vs = self.val_struct
        start = pos
        cid = rid(mm, pos)[0]
        pos += I + 4
        sup, loader, signers, pd = struct.unpack_from(">" + self.ID * 4, mm, pos)
        pos += 6 * I
        inst_size, ncp = struct.unpack_from(">IH", mm, pos)
        pos += 6
        cp_refs = []
        for _ in range(ncp):
            t = mm[pos + 2]
            pos += 3
            if t == T_OBJECT:
                v = rid(mm, pos)[0]
                if v:
                    cp_refs.append(v)
            pos += tsize[t]
        nst = struct.unpack_from(">H", mm, pos)[0]
        pos += 2
        statics = []
        for _ in range(nst):
            nsid = rid(mm, pos)[0]
            t = mm[pos + I]
            pos += I + 1
            statics.append((nsid, t, vs[t].unpack_from(mm, pos)[0]))
            pos += tsize[t]
        nf = struct.unpack_from(">H", mm, pos)[0]
        pos += 2
        fields = []
        for _ in range(nf):
            fields.append((rid(mm, pos)[0], mm[pos + I]))
            pos += I + 1
        c = ClassInfo(len(self.classes), cid)
        c.super_id, c.loader_id, c.signers_id, c.pd_id = sup, loader, signers, pd
        c.inst_size = inst_size
        c.statics = statics
        c.fields = fields
        c.cp_refs = cp_refs
        self.classes.append(c)
        # 클래스 객체(java.lang.Class mirror)도 힙 객체로 등록
        self.obj_id.append(cid)
        self.obj_off.append(start)
        self.obj_kind.append(3)
        self.obj_cls.append(1)
        self.obj_len.append(c.ci)
        return pos

    # ------------------------------------------------------------------ class resolution
    def resolve_classes(self):
        strings = self.strings
        classes = self.classes
        by_id = {}
        for c in classes:
            sid = self.class_name_sid.get(c.cid)
            raw = strings.get(sid) if sid is not None else None
            c.name = java_name(raw) if raw else "<class@0x%x>" % c.cid
            # 정적 필드/인스턴스 필드 이름 id -> 문자열
            c.statics = [(strings.get(n, "?"), t, v) for (n, t, v) in c.statics]
            c.fields = [(strings.get(n, "?"), t) for (n, t) in c.fields]
            c.is_array = c.name.endswith("[]")
            by_id[c.cid] = c
        self.class_by_id = by_id
        for c in classes:
            c.sup = by_id.get(c.super_id) if c.super_id else None

        I = self.idsize
        tsize = self.tsize
        for c in classes:
            fm = {}
            ref_fields = []
            fmt = [">"]
            pad = off = prim = 0
            k = c
            depth = 0
            while k is not None and depth < 64:
                for (nm, t) in k.fields:
                    sz = tsize[t] if 0 <= t < 12 else 0
                    if nm not in fm:
                        fm[nm] = (t, off)
                    if t == T_OBJECT:
                        if pad:
                            fmt.append("%dx" % pad)
                            pad = 0
                        fmt.append(self.ID)
                        ref_fields.append((nm, off))
                    else:
                        pad += sz
                        prim += sz
                    off += sz
                if k.name == "java.lang.ref.Reference":
                    c.is_reference = True
                k = k.sup
                depth += 1
            c.field_map = fm
            c.ref_fields = ref_fields
            c.n_refs = len(ref_fields)
            c.prim_bytes = prim
            c.ref_struct = struct.Struct("".join(fmt)) if ref_fields else None

        # 기본형 배열 클래스 (덤프에 없으면 가상 클래스 생성)
        name_to_ci = {}
        for c in classes:
            name_to_ci.setdefault(c.name, c.ci)
        self.prim_array_ci = {}
        for et, pname in PRIM_NAME.items():
            nm = pname + "[]"
            ci = name_to_ci.get(nm)
            if ci is None:
                ci = self._synthetic_class(nm)
                name_to_ci[nm] = ci
            self.prim_array_ci[et] = ci
            classes[ci].elem_size = PRIM_SIZE[et]
        self.unknown_ci = self._synthetic_class("<unknown class>")
        jlc = name_to_ci.get("java.lang.Class")
        if jlc is None:
            jlc = self._synthetic_class("java.lang.Class")
        self.class_class_ci = jlc
        self.name_to_ci = name_to_ci

        # 객체별 클래스 인덱스 (기본형 배열은 원소 타입 코드 4~11, 클래스 객체는 1 을 키로 사용)
        cls_index = dict((c.cid, c.ci) for c in classes if not c.synthetic)
        for et, ci in self.prim_array_ci.items():
            cls_index[et] = ci
        cls_index[1] = jlc
        self.obj_ci = array("i", map(cls_index.get, self.obj_cls, _repeat(self.unknown_ci)))
        self.obj_ci[0] = self.unknown_ci
        del self.obj_cls

    def _synthetic_class(self, name):
        c = ClassInfo(len(self.classes), 0, name)
        c.synthetic = True
        c.is_array = name.endswith("[]")
        self.classes.append(c)
        return c.ci

    # ------------------------------------------------------------------ layout / oops
    def detect_layout(self, forced="auto"):
        if forced != "auto":
            self.layout = Layout(forced)
            self.layout_note = "사용자 지정 (--oops %s)" % forced
            return
        if self.idsize == 4:
            self.layout = Layout("32bit")
            self.layout_note = "identifier 4바이트 → 32비트 레이아웃"
            return
        # 같은 영역 안에서 연속으로 덤프된 객체의 주소 차이 = 실제 객체 크기.
        # 압축/비압축 두 가설로 계산한 크기 중 어느 쪽과 더 자주 일치하는지 투표한다.
        ids, kinds, lens, ocis = self.obj_id, self.obj_kind, self.obj_len, self.obj_ci
        classes = self.classes
        n = len(ids)
        c_lay, u_lay = Layout("compressed"), Layout("uncompressed")

        def est(i, lay):
            k = kinds[i]
            c = classes[ocis[i]]
            if k == 0:
                return (lay.hdr + c.n_refs * lay.ref + c.prim_bytes + 7) & ~7
            if k == 1:
                return (lay.arr + lens[i] * lay.ref + 7) & ~7
            if k == 2:
                return (lay.arr + lens[i] * c.elem_size + 7) & ~7
            return None

        votes_c = votes_u = 0
        chunks = 40
        span = 4000
        starts = sorted(set(max(1, (n - span) * j // chunks) for j in range(chunks)))
        for s in starts:
            for i in range(s, min(n - 1, s + span)):
                if kinds[i] == 3 or kinds[i + 1] == 3:
                    continue
                d = ids[i + 1] - ids[i]
                if d <= 0 or d > 65536:
                    continue
                a, b = est(i, c_lay), est(i, u_lay)
                if a == b:
                    continue
                if d == a:
                    votes_c += 1
                elif d == b:
                    votes_u += 1
        if votes_c + votes_u >= 50:
            mode = "compressed" if votes_c >= votes_u else "uncompressed"
            self.layout_note = "주소 간격 투표 (압축 %d : 비압축 %d)" % (votes_c, votes_u)
        else:
            max_addr = max(islice(ids, 1, None)) if n > 1 else 0
            mode = "compressed" if max_addr < (32 << 30) else "uncompressed"
            self.layout_note = "주소 범위 기반 추정 (최대 주소 0x%x)" % max_addr
        self.layout = Layout(mode)

    # ------------------------------------------------------------------ graph
    def _class_tables(self):
        lay = self.layout
        classes = self.classes
        get = self.index_of.get
        jlc = classes[self.class_class_ci]
        class_obj_base = lay.hdr + jlc.n_refs * lay.ref + jlc.prim_bytes
        tsize = self.tsize
        c_inst, c_elem, c_cshallow, c_crefs = [], [], [], []
        for c in classes:
            c.node = 0 if c.synthetic else get(c.cid, 0)
            c_inst.append((lay.hdr + c.n_refs * lay.ref + c.prim_bytes + 7) & ~7)
            if c.elem_size:
                c_elem.append(c.elem_size)
            elif c.is_array:
                c_elem.append(lay.ref)
            else:
                c_elem.append(0)
            st = 0
            refs = [c.super_id, c.loader_id, c.signers_id, c.pd_id]
            for (_nm, t, v) in c.statics:
                if t == T_OBJECT:
                    st += lay.ref
                    refs.append(v)
                else:
                    st += tsize[t] if 0 <= t < 12 else 0
            refs.extend(c.cp_refs)
            c_cshallow.append((class_obj_base + st + 7) & ~7)
            c_crefs.append(refs)
        return c_inst, c_elem, c_cshallow, c_crefs

    def build_graph(self, with_edges=True):
        log = self.log
        n = len(self.obj_id)
        self.n = n
        log("객체 인덱스 생성 (%s개)" % format(n - 1, ","))
        self.index_of = index_of = dict(zip(islice(self.obj_id, 1, None), range(1, n)))
        if len(index_of) != n - 1:
            self.warn("중복된 object id %d개 발견" % (n - 1 - len(index_of)))
        get = index_of.get
        c_inst, c_elem, c_cshallow, c_crefs = self._class_tables()
        classes = self.classes
        c_struct = [c.ref_struct for c in classes]
        c_node = [c.node for c in classes]
        mm = self.mm
        I = self.idsize
        arr = self.layout.arr
        ref = self.layout.ref
        kinds, offs, lens, ocis = self.obj_kind, self.obj_off, self.obj_len, self.obj_ci
        shallow = array("q", [0])
        sh_a = shallow.append
        log("객체 그래프 생성%s" % ("" if with_edges else " (shallow 크기만)"))
        if not with_edges:
            for i in range(1, n):
                k = kinds[i]
                if k == 0:
                    sh_a(c_inst[ocis[i]])
                elif k == 3:
                    sh_a(c_cshallow[lens[i]])
                else:
                    sh_a((arr + lens[i] * (c_elem[ocis[i]] if k == 2 else ref) + 7) & ~7)
            self.shallow = shallow
            return

        targets = array("i")
        ext = targets.extend
        t_a = targets.append
        root_nodes = sorted(set(filter(None, map(get, (r[1] for r in self.roots)))))
        if not root_nodes:
            self.warn("GC Root 정보가 없습니다 - 모든 클래스를 루트로 간주합니다")
            root_nodes = [c.node for c in classes if c.node]
        ext(root_nodes)
        es = array("q", [0, len(targets)])
        es_a = es.append
        swap = sys.byteorder == "little"
        idcode = self.id_array_code
        step = max(n // 10, 1)
        for i in range(1, n):
            k = kinds[i]
            ci = ocis[i]
            if k == 0:
                sh_a(c_inst[ci])
                st = c_struct[ci]
                if st is not None:
                    ext(filter(None, map(get, st.unpack_from(mm, offs[i]))))
                cn = c_node[ci]
                if cn:
                    t_a(cn)
            elif k == 2:
                sh_a((arr + lens[i] * c_elem[ci] + 7) & ~7)
            elif k == 1:
                cnt = lens[i]
                sh_a((arr + cnt * ref + 7) & ~7)
                if cnt:
                    o = offs[i]
                    a = array(idcode)
                    a.frombytes(mm[o:o + cnt * I])
                    if swap:
                        a.byteswap()
                    ext(filter(None, map(get, a)))
                cn = c_node[ci]
                if cn:
                    t_a(cn)
            else:
                cidx = lens[i]
                sh_a(c_cshallow[cidx])
                ext(filter(None, map(get, c_crefs[cidx])))
            es_a(len(targets))
            if i % step == 0:
                log("  그래프 %3d%%  (참조 %s개)" % (i * 100 // n, format(len(targets), ",")))
        self.shallow = shallow
        self.es = es
        self.targets = targets
        log("참조 %s개" % format(len(targets), ","))

    # ------------------------------------------------------------------ dominators
    def compute_dominators(self):
        """Lengauer-Tarjan (path compression) - 반복문 구현. dfnum 공간에서 계산."""
        log = self.log
        n = self.n
        es, tg = self.es, self.targets
        log("도달 가능성 분석 (DFS)")
        dfnum = [-1] * n
        dfnum[0] = 0
        vertex = [0]
        parent = [0]
        indeg = [0]  # dfnum 공간 진입 차수 (도달 가능한 소스만)
        stack_v = [0]
        stack_d = [0]
        stack_p = [es[0]]
        v_a = vertex.append
        p_a = parent.append
        i_a = indeg.append
        while stack_v:
            v = stack_v[-1]
            p = stack_p[-1]
            e = es[v + 1]
            while p < e:
                w = tg[p]
                p += 1
                dw = dfnum[w]
                if dw < 0:
                    stack_p[-1] = p
                    dw = len(vertex)
                    dfnum[w] = dw
                    v_a(w)
                    p_a(stack_d[-1])
                    i_a(1)
                    stack_v.append(w)
                    stack_d.append(dw)
                    stack_p.append(es[w])
                    break
                indeg[dw] += 1
            else:
                stack_v.pop()
                stack_d.pop()
                stack_p.pop()
        N = len(vertex)
        self.N = N
        log("도달 가능 객체 %s / %s" % (format(N - 1, ","), format(n - 1, ",")))

        log("역참조 인덱스 생성")
        ps = array("q", [0])
        ps.extend(accumulate(indeg))
        del indeg
        preds = array("i", bytes(4 * ps[-1]))
        fill = list(islice(ps, 0, N))
        for dv in range(N):
            v = vertex[dv]
            for w in tg[es[v]:es[v + 1]]:
                dw = dfnum[w]
                q = fill[dw]
                preds[q] = dv
                fill[dw] = q + 1
        del fill
        self.preds, self.ps = preds, ps

        log("Dominator tree 계산 (Lengauer-Tarjan)")
        semi = list(range(N))
        best = semi[:]
        ancestor = [-1] * N
        idom = [0] * N
        bhead = [-1] * N
        bnext = [-1] * N

        def evalnode(v):
            a = ancestor[v]
            if ancestor[a] >= 0:
                stk = [v]
                x = a
                while ancestor[ancestor[x]] >= 0:
                    stk.append(x)
                    x = ancestor[x]
                while stk:
                    y = stk.pop()
                    ay = ancestor[y]
                    b = best[ay]
                    if semi[b] < semi[best[y]]:
                        best[y] = b
                    ancestor[y] = ancestor[ay]
            return best[v]

        step = max(N // 10, 1)
        for w in range(N - 1, 0, -1):
            p = parent[w]
            s = p
            for v in preds[ps[w]:ps[w + 1]]:
                if v <= w:
                    if v < s:
                        s = v
                else:
                    a = ancestor[v]
                    if ancestor[a] >= 0:
                        stk = [v]
                        x = a
                        while ancestor[ancestor[x]] >= 0:
                            stk.append(x)
                            x = ancestor[x]
                        while stk:
                            y = stk.pop()
                            ay = ancestor[y]
                            b = best[ay]
                            if semi[b] < semi[best[y]]:
                                best[y] = b
                            ancestor[y] = ancestor[ay]
                    t = semi[best[v]]
                    if t < s:
                        s = t
            semi[w] = s
            bnext[w] = bhead[s]
            bhead[s] = w
            ancestor[w] = p
            v = bhead[p]
            if v >= 0:
                while v >= 0:
                    y = evalnode(v)
                    idom[v] = p if semi[y] == semi[v] else ~y
                    v = bnext[v]
                bhead[p] = -1
            if w % step == 0:
                log("  dominator %3d%%" % ((N - w) * 100 // N))
        for w in range(1, N):
            d = idom[w]
            if d < 0:
                idom[w] = idom[~d]
        del semi, best, ancestor, bhead, bnext, parent

        log("Retained 크기 계산")
        rs = list(map(self.shallow.__getitem__, vertex))
        rs[0] = 0
        for w in range(N - 1, 0, -1):
            rs[idom[w]] += rs[w]
        self.dfnum, self.vertex, self.idom, self.rs = dfnum, vertex, idom, rs

        # dominator tree 자식 목록 (CSR)
        cnt = [0] * (N + 1)
        for d in islice(idom, 1, None):
            cnt[d + 1] += 1
        cs = list(accumulate(cnt))
        ch = [0] * (N - 1 if N > 1 else 0)
        fill = cs[:]
        for w in range(1, N):
            d = idom[w]
            q = fill[d]
            ch[q] = w
            fill[d] = q + 1
        self.cs, self.ch = cs, ch
        # 더 이상 필요 없는 정방향 그래프 해제
        del self.es, self.targets

    # ------------------------------------------------------------------ object helpers
    def children(self, d):
        return self.ch[self.cs[d]:self.cs[d + 1]]

    def read_value(self, t, pos):
        return self.val_struct[t].unpack_from(self.mm, pos)[0]

    def field(self, node, name):
        """인스턴스 필드 값 (참조면 object id)"""
        if node <= 0 or self.obj_kind[node] != K_INSTANCE:
            return None
        c = self.classes[self.obj_ci[node]]
        fm = c.field_map.get(name)
        if fm is None:
            return None
        t, off = fm
        return self.read_value(t, self.obj_off[node] + off)

    def field_node(self, node, path):
        """'map.table' 같은 경로를 따라가 참조 노드를 반환 (없으면 0)"""
        for part in path.split("."):
            v = self.field(node, part)
            if not v:
                return 0
            node = self.index_of.get(v, 0)
            if not node:
                return 0
        return node

    def cls_name(self, node):
        if self.obj_kind[node] == K_CLASS:
            return "java.lang.Class"
        return self.classes[self.obj_ci[node]].name

    def string_value(self, node, limit=200):
        """java.lang.String 인스턴스의 문자열 (JDK 8 char[] / JDK 9+ byte[]+coder 모두 지원)"""
        vnode = self.field_node(node, "value")
        if not vnode or self.obj_kind[vnode] != K_PRIMARRAY:
            return None
        cnt = self.obj_len[vnode]
        off = self.obj_off[vnode]
        if not off:
            return None
        es = self.classes[self.obj_ci[vnode]].elem_size
        if es == 2:  # char[] (HPROF는 big-endian)
            raw = self.mm[off:off + min(cnt, limit) * 2]
            return raw.decode("utf-16-be", "replace")
        coder = self.field(node, "coder")
        if coder == 1:
            raw = self.mm[off:off + min(cnt, limit * 2) & ~1]
            return raw.decode("utf-16-le" if sys.byteorder == "little" else "utf-16-be", "replace")
        return self.mm[off:off + min(cnt, limit)].decode("latin-1")

    def describe(self, node):
        """객체를 사람이 읽을 수 있게 짧게 설명"""
        k = self.obj_kind[node]
        if k == K_CLASS:
            return "class " + self.classes[self.obj_len[node]].name
        c = self.classes[self.obj_ci[node]]
        if k == K_OBJARRAY or k == K_PRIMARRAY:
            return "length=%s" % format(self.obj_len[node], ",")
        name = c.name
        try:
            if name == "java.lang.String":
                s = self.string_value(node, 80)
                return None if s is None else '"%s"' % _short(s, 80)
            if name in BOXED:
                v = self.field(node, "value")
                return "value=%s" % (chr(v) if name == "java.lang.Character" and v is not None else v)
            if self.thread_cls(c):
                nm = self.thread_name(node)
                return 'thread "%s"' % nm if nm is not None else None
            base = self.collection_base(c.ci)
            if base:
                size, cap = self.collection_size(node, base)
                if size is not None:
                    return "size=%s" % format(size, ",") + (" capacity=%s" % format(cap, ",") if cap else "")
            if "name" in c.field_map and self.is_classloader(c):
                sn = self.field_node(node, "name")
                if sn:
                    s = self.string_value(sn, 60)
                    if s:
                        return 'name="%s"' % s
        except Exception:
            return None
        return None

    def thread_cls(self, c):
        k = c
        while k is not None:
            if k.name == "java.lang.Thread":
                return True
            k = k.sup
        return False

    def is_classloader(self, c):
        k = c
        while k is not None:
            if k.name == "java.lang.ClassLoader":
                return True
            k = k.sup
        return False

    def thread_name(self, node):
        sn = self.field_node(node, "name")
        if not sn:
            return None
        s = self.string_value(sn, 120)
        return s

    def collection_base(self, ci):
        cache = getattr(self, "_coll_cache", None)
        if cache is None:
            cache = self._coll_cache = {}
        if ci in cache:
            return cache[ci]
        k = self.classes[ci]
        base = None
        depth = 0
        while k is not None and depth < 32:
            if k.name in COLLECTION_SPECS:
                base = k.name
                break
            k = k.sup
            depth += 1
        cache[ci] = base
        return base

    def _path_value(self, node, path):
        parts = path.split(".")
        for p in parts[:-1]:
            node = self.field_node(node, p)
            if not node:
                return None
        last = parts[-1]
        if last == "length":
            return self.obj_len[node] if node else None
        return self.field(node, last)

    def collection_size(self, node, base):
        size_path, cap_path = COLLECTION_SPECS[base]
        cap = None
        if size_path == "<deque>":
            en = self.field_node(node, "elements")
            if not en:
                return None, None
            L = self.obj_len[en]
            h, t = self.field(node, "head"), self.field(node, "tail")
            size = ((t - h) % L) if (L and h is not None and t is not None) else None
            return size, L
        size = self._path_value(node, size_path)
        if cap_path:
            cn = self.field_node(node, cap_path)
            cap = self.obj_len[cn] if cn else 0
        return size, cap

    def ref_label(self, u, v):
        """노드 u 가 노드 v 를 참조하는 방식 (필드명/배열 인덱스)"""
        mm = self.mm
        vid = self.obj_id[v]
        k = self.obj_kind[u]
        rid = self.s_id.unpack_from
        if k == K_INSTANCE:
            c = self.classes[self.obj_ci[u]]
            base = self.obj_off[u]
            names = [nm for (nm, fo) in c.ref_fields if rid(mm, base + fo)[0] == vid]
            if names:
                return ", ".join("." + nm for nm in names[:3])
            return "<class>" if self.classes[self.obj_ci[u]].node == v else None
        if k == K_OBJARRAY:
            a = array(self.id_array_code)
            o = self.obj_off[u]
            a.frombytes(mm[o:o + self.obj_len[u] * self.idsize])
            if sys.byteorder == "little":
                a.byteswap()
            try:
                return "[%d]" % a.index(vid)
            except ValueError:
                return "<class>"
        if k == K_CLASS:
            c = self.classes[self.obj_len[u]]
            names = [nm for (nm, t, val) in c.statics if t == T_OBJECT and val == vid]
            if names:
                return ", ".join("static " + nm for nm in names[:3])
            if vid == c.super_id:
                return "<super>"
            if vid == c.loader_id:
                return "<classloader>"
            if vid == c.signers_id:
                return "<signers>"
            if vid == c.pd_id:
                return "<protection domain>"
            if vid in c.cp_refs:
                return "<constant pool>"
        return None

    def strong_edge(self, u, v):
        """GC Root 경로 탐색용: weak/soft referent 와 인스턴스→클래스 가상 참조는 제외"""
        if self.obj_kind[u] != K_INSTANCE:
            return True
        c = self.classes[self.obj_ci[u]]
        vid = self.obj_id[v]
        base = self.obj_off[u]
        rid = self.s_id.unpack_from
        names = [nm for (nm, fo) in c.ref_fields if rid(self.mm, base + fo)[0] == vid]
        if not names:
            return False
        if c.is_reference and all(nm == "referent" for nm in names):
            return False
        return True

    def path_to_root(self, d, max_visit=500000):
        """dfnum d 까지의 최단 GC Root 경로 [루트객체, ..., d] (dfnum 리스트)"""
        preds, ps, vertex = self.preds, self.ps, self.vertex
        for strict in (True, False):
            nxt_of = {d: -1}
            frontier = [d]
            found = None
            while frontier and found is None and len(nxt_of) < max_visit:
                new = []
                for v in frontier:
                    for u in preds[ps[v]:ps[v + 1]]:
                        if u == 0:
                            found = v
                            break
                        if u in nxt_of:
                            continue
                        if strict and not self.strong_edge(vertex[u], vertex[v]):
                            continue
                        nxt_of[u] = v
                        new.append(u)
                    if found is not None:
                        break
                frontier = new
            if found is not None:
                path = [found]
                x = found
                while x != d:
                    x = nxt_of[x]
                    path.append(x)
                return path
        return None


def _repeat(x):
    while True:
        yield x


def _short(s, n):
    s = s.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    return s if len(s) <= n else s[:n] + "…"
