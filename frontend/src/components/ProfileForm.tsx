import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { UserInput } from "../types";
import { theme } from "../theme";

const LEVELS = ["beginner", "intermediate", "advanced"];

interface Props {
  initial?: { display_name?: string; level?: string | null; interests?: string | null };
  submitLabel: string;
  submitting?: boolean;
  onSubmit: (input: UserInput) => void;
}

export function ProfileForm({ initial, submitLabel, submitting, onSubmit }: Props) {
  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [level, setLevel] = useState<string>(initial?.level ?? "beginner");
  const [interests, setInterests] = useState(initial?.interests ?? "");

  const canSubmit = displayName.trim().length > 0 && !submitting;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit({
      display_name: displayName.trim(),
      level,
      interests: interests.trim() || undefined,
    });
  };

  return (
    <View>
      <Text style={styles.label}>Display name</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. Maya"
        placeholderTextColor={theme.colors.muted}
        value={displayName}
        onChangeText={setDisplayName}
        maxLength={80}
      />

      <Text style={styles.label}>Your English level</Text>
      <View style={styles.levels}>
        {LEVELS.map((lvl) => {
          const active = lvl === level;
          return (
            <Pressable
              key={lvl}
              onPress={() => setLevel(lvl)}
              style={[styles.levelChip, active && styles.levelChipActive]}
            >
              <Text style={[styles.levelText, active && styles.levelTextActive]}>{lvl}</Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.label}>Interests (comma separated)</Text>
      <TextInput
        style={styles.input}
        placeholder="travel, music, food"
        placeholderTextColor={theme.colors.muted}
        value={interests}
        onChangeText={setInterests}
        maxLength={300}
      />

      <Pressable
        onPress={submit}
        disabled={!canSubmit}
        style={[styles.button, !canSubmit && styles.buttonDisabled]}
      >
        <Text style={styles.buttonText}>{submitting ? "Saving..." : submitLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.text,
    marginTop: theme.spacing(2),
    marginBottom: theme.spacing(1),
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 8,
    paddingHorizontal: theme.spacing(1.25),
    paddingVertical: theme.spacing(1),
    fontSize: 15,
    color: theme.colors.text,
    backgroundColor: theme.colors.card,
  },
  levels: {
    flexDirection: "row",
    gap: theme.spacing(1),
  },
  levelChip: {
    flex: 1,
    paddingVertical: theme.spacing(1),
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.card,
    alignItems: "center",
  },
  levelChipActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  levelText: {
    fontSize: 13,
    color: theme.colors.text,
    textTransform: "capitalize",
  },
  levelTextActive: {
    color: "#FFFFFF",
    fontWeight: "600",
  },
  button: {
    marginTop: theme.spacing(3),
    backgroundColor: theme.colors.primary,
    borderRadius: 8,
    paddingVertical: theme.spacing(1.25),
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: "#FFFFFF",
    fontWeight: "700",
    fontSize: 15,
  },
});
