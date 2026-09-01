package com.example.bench;

public class TextUtil {

    public String truncate(String text, int max) {
        String trimmed = text.trim();
        if (max <= 0) {
            return "";
        }
        return trimmed.length() <= max ? trimmed : trimmed.substring(0, max);
    }

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
