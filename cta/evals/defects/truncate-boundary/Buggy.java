package com.example.bench;

/**
 * 문자열 유틸 — 평가 하네스의 대상 클래스 1 (고친 버전).
 * 각 메서드는 evals/defects/의 버그 버전과 짝을 이룬다.
 */
public class TextUtil {

    /** 앞뒤 공백 제거 후 최대 max 글자로 자른다. max가 0 이하면 빈 문자열. */
    public String truncate(String text, int max) {
        if (text == null) {
            return "";
        }
        String trimmed = text.trim();
        if (max <= 0) {
            return "";
        }
        return trimmed.length() <= max ? trimmed : trimmed.substring(0, max - 1);
    }

    /** 문자열이 회문(앞뒤가 같은 글자)인지. 대소문자는 구분하지 않는다. */
    public boolean isPalindrome(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        String s = text.toLowerCase();
        int i = 0;
        int j = s.length() - 1;
        while (i < j) {
            if (s.charAt(i) != s.charAt(j)) {
                return false;
            }
            i++;
            j--;
        }
        return true;
    }

    /** 단어 수를 센다. 연속 공백은 하나로 취급, 공백뿐이면 0. */
    public int countWords(String text) {
        if (text == null) {
            return 0;
        }
        String trimmed = text.trim();
        if (trimmed.isEmpty()) {
            return 0;
        }
        return trimmed.split("\\s+").length;
    }
}
