import { useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { ProfileForm } from "../components/ProfileForm";
import { useProfile } from "../context/ProfileContext";
import type { UserInput } from "../types";
import { theme } from "../theme";

export function ProfileScreen() {
  const { profile, saveProfile, signOut } = useProfile();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!profile) return null; // RootNavigator only mounts this when a profile exists.

  const onSubmit = async (input: UserInput) => {
    setSaving(true);
    setError(null);
    try {
      await saveProfile(input);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  };

  const confirmSignOut = () => {
    Alert.alert("Start over?", "This clears your profile on this device.", [
      { text: "Cancel", style: "cancel" },
      { text: "Start over", style: "destructive", onPress: () => void signOut() },
    ]);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.name}>{profile.display_name}</Text>
        <View style={styles.tags}>
          {profile.level ? <Text style={[styles.tag, styles.levelTag]}>{profile.level}</Text> : null}
          {(profile.interests ?? "")
            .split(",")
            .map((i) => i.trim())
            .filter(Boolean)
            .map((interest) => (
              <Text key={interest} style={styles.tag}>
                {interest}
              </Text>
            ))}
        </View>
      </View>

      {editing ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Edit profile</Text>
          <ProfileForm
            initial={profile}
            submitLabel="Save changes"
            submitting={saving}
            onSubmit={onSubmit}
          />
          {error ? <Text style={styles.error}>Could not save ({error}).</Text> : null}
          <Pressable onPress={() => setEditing(false)} style={styles.linkButton}>
            <Text style={styles.linkText}>Cancel</Text>
          </Pressable>
        </View>
      ) : (
        <>
          <Pressable onPress={() => setEditing(true)} style={styles.button}>
            <Text style={styles.buttonText}>Edit profile</Text>
          </Pressable>
          <Pressable onPress={confirmSignOut} style={[styles.button, styles.danger]}>
            <Text style={[styles.buttonText, styles.dangerText]}>Start over</Text>
          </Pressable>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.spacing(2),
  },
  card: {
    backgroundColor: theme.colors.card,
    borderRadius: theme.radius,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(2),
    marginBottom: theme.spacing(2),
  },
  name: {
    fontSize: 22,
    fontWeight: "800",
    color: theme.colors.text,
  },
  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
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
  levelTag: {
    color: "#FFFFFF",
    backgroundColor: theme.colors.primary,
    textTransform: "capitalize",
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: theme.colors.text,
  },
  button: {
    backgroundColor: theme.colors.card,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingVertical: theme.spacing(1.25),
    alignItems: "center",
    marginBottom: theme.spacing(1.5),
  },
  buttonText: {
    color: theme.colors.text,
    fontWeight: "700",
  },
  danger: {
    borderColor: "#FECACA",
    backgroundColor: "#FEF2F2",
  },
  dangerText: {
    color: theme.colors.danger,
  },
  linkButton: {
    alignItems: "center",
    paddingVertical: theme.spacing(1.5),
  },
  linkText: {
    color: theme.colors.muted,
    fontWeight: "600",
  },
  error: {
    marginTop: theme.spacing(1.5),
    color: theme.colors.danger,
  },
});
