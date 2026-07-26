import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { createNote, fetchNotes } from "../api/notes";
import { NoteCard } from "../components/NoteCard";
import type { SentenceNote } from "../types";
import { theme } from "../theme";

export function NotesScreen() {
  const [notes, setNotes] = useState<SentenceNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [original, setOriginal] = useState("");
  const [improved, setImproved] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      setNotes(await fetchNotes());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = useCallback(async () => {
    if (!original.trim() && !improved.trim()) return;
    setSaving(true);
    try {
      await createNote({
        original_text: original.trim() || undefined,
        improved_text: improved.trim() || undefined,
        source: "self",
      });
      setOriginal("");
      setImproved("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }, [original, improved, load]);

  return (
    <View style={styles.container}>
      <View style={styles.form}>
        <TextInput
          style={styles.input}
          placeholder="What you said..."
          placeholderTextColor={theme.colors.muted}
          value={original}
          onChangeText={setOriginal}
        />
        <TextInput
          style={styles.input}
          placeholder="A better sentence..."
          placeholderTextColor={theme.colors.muted}
          value={improved}
          onChangeText={setImproved}
        />
        <Pressable
          onPress={onSave}
          disabled={saving}
          style={[styles.button, saving && styles.buttonDisabled]}
        >
          <Text style={styles.buttonText}>{saving ? "Saving..." : "Save note"}</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator style={styles.loader} color={theme.colors.primary} />
      ) : error ? (
        <Text style={styles.error}>Cannot reach the API ({error}). Is the backend running?</Text>
      ) : (
        <FlatList
          data={notes}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <NoteCard note={item} />}
          ListEmptyComponent={<Text style={styles.empty}>No notes yet. Save your first one!</Text>}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    paddingHorizontal: theme.spacing(2),
    paddingTop: theme.spacing(2),
  },
  form: {
    backgroundColor: theme.colors.card,
    borderRadius: theme.radius,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(1.5),
    marginBottom: theme.spacing(2),
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 8,
    paddingHorizontal: theme.spacing(1.25),
    paddingVertical: theme.spacing(1),
    fontSize: 14,
    color: theme.colors.text,
    marginBottom: theme.spacing(1),
  },
  button: {
    backgroundColor: theme.colors.primary,
    borderRadius: 8,
    paddingVertical: theme.spacing(1.25),
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: "#FFFFFF",
    fontWeight: "700",
  },
  list: {
    paddingBottom: theme.spacing(3),
  },
  loader: {
    marginTop: theme.spacing(3),
  },
  empty: {
    marginTop: theme.spacing(3),
    color: theme.colors.muted,
    textAlign: "center",
  },
  error: {
    marginTop: theme.spacing(3),
    color: theme.colors.danger,
  },
});
