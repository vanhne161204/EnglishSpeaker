import { useCallback, useLayoutEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import { fetchRoom } from "../api/rooms";
import { fetchTopics } from "../api/topics";
import type { RoomsStackParamList } from "../navigation/RoomsStack";
import type { Room, Topic } from "../types";
import { theme } from "../theme";

type DetailRoute = RouteProp<RoomsStackParamList, "RoomDetail">;
type Nav = NativeStackNavigationProp<RoomsStackParamList, "RoomDetail">;

/**
 * Room lobby / hub. Three sections:
 *  1. People in the room + mic status
 *  2. The room's topic and documents related to it
 *  3. Three action buttons (Text chat + two reserved)
 */
export function RoomDetailScreen() {
  const { room: initialRoom } = useRoute<DetailRoute>().params;
  const navigation = useNavigation<Nav>();

  const [room, setRoom] = useState<Room>(initialRoom);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [loadingTopic, setLoadingTopic] = useState(true);

  useLayoutEffect(() => {
    navigation.setOptions({ title: room.title });
  }, [navigation, room.title]);

  const load = useCallback(async () => {
    const [fresh, topics] = await Promise.all([
      fetchRoom(initialRoom.id).catch(() => initialRoom),
      fetchTopics().catch(() => [] as Topic[]),
    ]);
    setRoom(fresh);
    const match = fresh.topic
      ? (topics.find((t) => t.title.toLowerCase() === fresh.topic?.toLowerCase()) ?? null)
      : null;
    setTopic(match);
    setLoadingTopic(false);
  }, [initialRoom]);

  // Refresh the people count every time the lobby comes back into focus.
  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const isOneOnOne = room.kind === "one_on_one";

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Part 1 — people + mic status */}
      <View style={styles.card}>
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statValue}>
              👥 {room.participant_count}/{room.capacity}
            </Text>
            <Text style={styles.statLabel}>People in room</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.stat}>
            <Text style={styles.statValue}>🎤 Off</Text>
            <Text style={styles.statLabel}>Mic status</Text>
          </View>
        </View>
        <View style={styles.tags}>
          <Text style={[styles.tag, styles.kindTag]}>{isOneOnOne ? "1-on-1" : "Group"}</Text>
          <Text style={styles.tag}>{room.mode}</Text>
        </View>
      </View>

      {/* Part 2 — topic + related documents */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Topic</Text>
        <Text style={styles.topicTitle}>{topic?.title ?? room.topic ?? "Free talk"}</Text>
        {room.level ? <Text style={[styles.tag, styles.levelTag]}>{room.level}</Text> : null}
        {topic?.description ? <Text style={styles.topicDesc}>{topic.description}</Text> : null}

        <Text style={styles.docsTitle}>Related documents</Text>
        {loadingTopic ? (
          <ActivityIndicator color={theme.colors.primary} />
        ) : (
          <Text style={styles.docsEmpty}>
            No learning documents for this topic yet — materials added by an admin will appear here.
          </Text>
        )}
      </View>

      {/* Part 3 — three action buttons */}
      <View style={styles.actions}>
        <Pressable
          onPress={() => navigation.navigate("RoomChat", { room })}
          style={({ pressed }) => [styles.action, styles.actionPrimary, pressed && styles.pressed]}
        >
          <Text style={styles.actionPrimaryText}>💬</Text>
          <Text style={styles.actionPrimaryLabel}>Text chat</Text>
        </Pressable>
        <View style={[styles.action, styles.actionBlank]} />
        <View style={[styles.action, styles.actionBlank]} />
      </View>
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
  statsRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  stat: {
    flex: 1,
    alignItems: "center",
  },
  statDivider: {
    width: 1,
    alignSelf: "stretch",
    backgroundColor: theme.colors.border,
    marginVertical: theme.spacing(0.5),
  },
  statValue: {
    fontSize: 20,
    fontWeight: "800",
    color: theme.colors.text,
  },
  statLabel: {
    fontSize: 12,
    color: theme.colors.muted,
    marginTop: 2,
  },
  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing(0.75),
    marginTop: theme.spacing(1.5),
    justifyContent: "center",
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
    textTransform: "capitalize",
  },
  kindTag: {
    color: "#FFFFFF",
    backgroundColor: theme.colors.primary,
  },
  levelTag: {
    alignSelf: "flex-start",
    color: "#475569",
    backgroundColor: "#F1F5F9",
    marginTop: theme.spacing(1),
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  topicTitle: {
    fontSize: 22,
    fontWeight: "800",
    color: theme.colors.text,
    marginTop: 2,
  },
  topicDesc: {
    fontSize: 15,
    color: theme.colors.text,
    lineHeight: 22,
    marginTop: theme.spacing(1.5),
  },
  docsTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: theme.spacing(2.5),
    marginBottom: theme.spacing(1),
  },
  docsEmpty: {
    fontSize: 14,
    color: theme.colors.muted,
    lineHeight: 20,
  },
  actions: {
    flexDirection: "row",
    gap: theme.spacing(1.5),
  },
  action: {
    flex: 1,
    height: 88,
    borderRadius: theme.radius,
    alignItems: "center",
    justifyContent: "center",
  },
  actionPrimary: {
    backgroundColor: theme.colors.primary,
  },
  actionPrimaryText: {
    fontSize: 24,
  },
  actionPrimaryLabel: {
    color: "#FFFFFF",
    fontWeight: "700",
    fontSize: 14,
    marginTop: 4,
  },
  actionBlank: {
    backgroundColor: theme.colors.card,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: theme.colors.border,
  },
  pressed: {
    opacity: 0.85,
  },
});
