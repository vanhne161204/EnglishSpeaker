import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Room } from "../types";
import { theme } from "../theme";

export function RoomCard({ room, onPress }: { room: Room; onPress?: () => void }) {
  const isOneOnOne = room.kind === "one_on_one";
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
    >
      <View style={styles.header}>
        <Text style={styles.title}>{room.title}</Text>
        <Text style={styles.participants}>
          👥 {room.participant_count}/{room.capacity}
        </Text>
      </View>
      <View style={styles.tags}>
        <Text style={[styles.tag, styles.kindTag]}>{isOneOnOne ? "1-on-1" : "Group"}</Text>
        {room.topic ? <Text style={styles.tag}>{room.topic}</Text> : null}
        {room.level ? <Text style={[styles.tag, styles.levelTag]}>{room.level}</Text> : null}
      </View>
    </Pressable>
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
  cardPressed: {
    opacity: 0.6,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    fontSize: 16,
    fontWeight: "600",
    color: theme.colors.text,
    flexShrink: 1,
  },
  participants: {
    fontSize: 13,
    color: theme.colors.muted,
    marginLeft: theme.spacing(1),
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
  kindTag: {
    color: "#FFFFFF",
    backgroundColor: theme.colors.primary,
  },
  levelTag: {
    color: "#475569",
    backgroundColor: "#F1F5F9",
    textTransform: "capitalize",
  },
});
