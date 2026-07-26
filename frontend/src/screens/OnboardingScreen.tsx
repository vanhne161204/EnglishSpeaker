import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text } from "react-native";
import { ProfileForm } from "../components/ProfileForm";
import { useProfile } from "../context/ProfileContext";
import type { UserInput } from "../types";
import { theme } from "../theme";

export function OnboardingScreen() {
  const { saveProfile } = useProfile();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (input: UserInput) => {
    setSaving(true);
    setError(null);
    try {
      // On success the navigator swaps to the main tabs automatically.
      await saveProfile(input);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Welcome to EnglishTalker 👋</Text>
        <Text style={styles.subtitle}>
          Set up a quick profile so we can find good people for you to practice with.
        </Text>

        <ProfileForm submitLabel="Start practicing" submitting={saving} onSubmit={onSubmit} />

        {error ? (
          <Text style={styles.error}>Could not create your profile ({error}). Is the API running?</Text>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.spacing(3),
    paddingTop: theme.spacing(8),
  },
  title: {
    fontSize: 26,
    fontWeight: "800",
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: 15,
    color: theme.colors.muted,
    marginTop: theme.spacing(1),
    lineHeight: 22,
  },
  error: {
    marginTop: theme.spacing(2),
    color: theme.colors.danger,
  },
});
