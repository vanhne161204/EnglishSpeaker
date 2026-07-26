import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { translate } from "../api/translate";
import type { TranslateResult } from "../types";
import { theme } from "../theme";

// How long to wait after the last keystroke before translating (Google-Translate-like).
const DEBOUNCE_MS = 450;

const LANGUAGES: Record<string, string> = {
  en: "English",
  vi: "Vietnamese",
};

/** Instant, in-room translator: type and the translation appears as you go. */
export function TranslatorPanel() {
  const [text, setText] = useState("");
  // Default: hear an English word in the room → see its Vietnamese meaning.
  const [source, setSource] = useState("en");
  const [target, setTarget] = useState("vi");
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [translating, setTranslating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against out-of-order responses when typing fast (last request wins).
  const requestId = useRef(0);

  const swap = () => {
    setSource(target);
    setTarget(source);
    setText(result?.translated_text ?? text);
    setResult(null);
  };

  useEffect(() => {
    const trimmed = text.trim();
    if (!trimmed) {
      setResult(null);
      setError(null);
      setTranslating(false);
      return;
    }

    const id = ++requestId.current;
    setTranslating(true);
    setError(null);

    const handle = setTimeout(async () => {
      try {
        const res = await translate({ text: trimmed, source_lang: source, target_lang: target });
        if (id === requestId.current) setResult(res);
      } catch (err) {
        if (id === requestId.current) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (id === requestId.current) setTranslating(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [text, source, target]);

  return (
    <View style={styles.panel}>
      <View style={styles.langBar}>
        <Text style={styles.langName}>{LANGUAGES[source]}</Text>
        <Pressable onPress={swap} hitSlop={8} style={styles.swapButton}>
          <Text style={styles.swapIcon}>⇄</Text>
        </Pressable>
        <Text style={styles.langName}>{LANGUAGES[target]}</Text>
      </View>

      <TextInput
        style={styles.input}
        placeholder={`Type in ${LANGUAGES[source]}...`}
        placeholderTextColor={theme.colors.muted}
        value={text}
        onChangeText={setText}
        multiline
      />

      <View style={styles.result}>
        {translating ? (
          <ActivityIndicator color={theme.colors.primary} />
        ) : error ? (
          <Text style={styles.error}>Translation failed ({error}).</Text>
        ) : result?.translated_text ? (
          <>
            <Text style={styles.resultText}>{result.translated_text}</Text>
            {result.provider === "stub" ? (
              <Text style={styles.resultNote}>
                Demo translator — set ANTHROPIC_API_KEY for real Claude translation.
              </Text>
            ) : null}
          </>
        ) : (
          <Text style={styles.resultPlaceholder}>Translation will appear here.</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: theme.colors.card,
    borderTopWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(1.5),
  },
  langBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing(1),
  },
  langName: {
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.text,
    textAlign: "center",
  },
  swapButton: {
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(0.5),
  },
  swapIcon: {
    fontSize: 20,
    color: theme.colors.primary,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 8,
    paddingHorizontal: theme.spacing(1.25),
    paddingVertical: theme.spacing(1),
    fontSize: 15,
    color: theme.colors.text,
    marginTop: theme.spacing(1),
    minHeight: 48,
    textAlignVertical: "top",
  },
  result: {
    marginTop: theme.spacing(1),
    padding: theme.spacing(1.5),
    backgroundColor: "#F0FDF4",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#BBF7D0",
    minHeight: 48,
    justifyContent: "center",
  },
  resultText: {
    fontSize: 16,
    color: theme.colors.text,
  },
  resultPlaceholder: {
    fontSize: 14,
    color: theme.colors.muted,
  },
  resultNote: {
    marginTop: theme.spacing(1),
    fontSize: 12,
    color: theme.colors.muted,
  },
  error: {
    color: theme.colors.danger,
  },
});
