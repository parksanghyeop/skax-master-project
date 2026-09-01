package com.example.bench;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/**
 * 기존 테스트 — 예열·few-shot 본보기용 최소 세트.
 * 평가 대상 메서드들의 테스트는 일부러 없다(에이전트가 만들 몫).
 */
class TextUtilTest {

    @Test
    void countWords_simpleSentence_returnsCount() {
        TextUtil util = new TextUtil();
        assertEquals(3, util.countWords("a b c"));
    }
}
