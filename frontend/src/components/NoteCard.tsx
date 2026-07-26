import { StyleSheet, Text, View } from "react-native";
import type { SentenceNote } from "../types";
import { theme } from "../theme";

export function NoteCard({ note }: { note: SentenceNote }) {
  return (
    <View style={styles.card}>
      {note.original_text ? <Text style={styles.original}>{note.original_text}</Text> : null}
      {note.improved_text ? <Text style={styles.improved}>✓ {note.improved_text}</Text> : null}
      <View style={styles.footer}>
        {note.topic ? <Text style={styles.tag}>{note.topic}</Text> : null}
        <Text style={styles.source}>{note.source}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.card,
    borderRadius: theme.radius,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(2),
    marginBottom: theme.spacing(1.5),
  },
  original: {
    fontSize: 14,
    color: theme.colors.muted,
    textDecorationLine: "line-through",
  },
  improved: {
    fontSize: 15,
    fontWeight: "600",
    color: theme.colors.text,
    marginTop: 4,
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: theme.spacing(1),
    gap: theme.spacing(0.75),
  },
  tag: {
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.primary,
    backgroundColor: "#E0F2FE",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    overflow: "hidden",
  },
  source: {
    fontSize: 11,
    color: theme.colors.muted,
    textTransform: "uppercase",
  },
});
