import { StyleSheet, Switch, Text, View } from "react-native";
import { theme } from "../theme";

interface ModeToggleProps {
  incognito: boolean;
  onChange: (incognito: boolean) => void;
}

/**
 * Normal / Incognito switch. When on, the user is in Incognito mode and only
 * sees Incognito rooms (PRD §7 — modes are a hard partition).
 */
export function ModeToggle({ incognito, onChange }: ModeToggleProps) {
  return (
    <View style={[styles.card, incognito && styles.cardIncognito]}>
      <View style={styles.textGroup}>
        <Text style={styles.icon}>{incognito ? "🕶️" : "🙂"}</Text>
        <View style={styles.labels}>
          <Text style={[styles.title, incognito && styles.textLight]}>
            {incognito ? "Incognito mode" : "Normal mode"}
          </Text>
          <Text style={[styles.subtitle, incognito && styles.subtitleLight]}>
            {incognito
              ? "Your identity is hidden. You only meet other incognito users."
              : "Your profile is visible to other normal-mode users."}
          </Text>
        </View>
      </View>
      <Switch
        value={incognito}
        onValueChange={onChange}
        trackColor={{ false: theme.colors.border, true: "#334155" }}
        thumbColor="#FFFFFF"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: theme.colors.card,
    borderRadius: theme.radius,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing(1.5),
    marginBottom: theme.spacing(2),
  },
  cardIncognito: {
    backgroundColor: "#0F172A",
    borderColor: "#0F172A",
  },
  textGroup: {
    flexDirection: "row",
    alignItems: "center",
    flexShrink: 1,
    paddingRight: theme.spacing(1),
  },
  icon: {
    fontSize: 22,
    marginRight: theme.spacing(1),
  },
  labels: {
    flexShrink: 1,
  },
  title: {
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.text,
  },
  subtitle: {
    fontSize: 12,
    color: theme.colors.muted,
    marginTop: 2,
  },
  textLight: {
    color: "#FFFFFF",
  },
  subtitleLight: {
    color: "#CBD5E1",
  },
});
