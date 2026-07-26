import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { matchOne, randomMatch } from "../api/match";
import { fetchRooms } from "../api/rooms";
import { ModeToggle } from "../components/ModeToggle";
import { RoomCard } from "../components/RoomCard";
import type { RoomsStackParamList } from "../navigation/RoomsStack";
import type { ConversationMode, Room, RoomKind } from "../types";
import { theme } from "../theme";

type KindFilter = "all" | RoomKind;

const KIND_FILTERS: { key: KindFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "group", label: "Group" },
  { key: "one_on_one", label: "1-on-1" },
];

type Nav = NativeStackNavigationProp<RoomsStackParamList, "RoomsList">;

export function RoomsScreen() {
  const navigation = useNavigation<Nav>();
  const [incognito, setIncognito] = useState(false);
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mode: ConversationMode = incognito ? "incognito" : "normal";

  const load = useCallback(async () => {
    try {
      setError(null);
      const kind = kindFilter === "all" ? undefined : kindFilter;
      setRooms(await fetchRooms(mode, kind));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [mode, kindFilter]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void load();
  }, [load]);

  const startMatch = useCallback(
    async (finder: typeof matchOne) => {
      setMatching(true);
      setError(null);
      try {
        const room = await finder({ mode });
        navigation.navigate("RoomDetail", { room });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setMatching(false);
      }
    },
    [mode, navigation],
  );

  return (
    <View style={styles.container}>
      <ModeToggle incognito={incognito} onChange={setIncognito} />

      <View style={styles.matchRow}>
        <Pressable
          onPress={() => startMatch(matchOne)}
          disabled={matching}
          style={[styles.matchButton, styles.matchPrimary, matching && styles.matchDisabled]}
        >
          <Text style={styles.matchPrimaryText}>🤝 Match 1-on-1</Text>
        </Pressable>
        <Pressable
          onPress={() => startMatch(randomMatch)}
          disabled={matching}
          style={[styles.matchButton, styles.matchSecondary, matching && styles.matchDisabled]}
        >
          <Text style={styles.matchSecondaryText}>🎲 Random</Text>
        </Pressable>
      </View>

      <Text style={styles.browseLabel}>Or browse open rooms</Text>

      <View style={styles.segment}>
        {KIND_FILTERS.map(({ key, label }) => {
          const active = key === kindFilter;
          return (
            <Pressable
              key={key}
              onPress={() => setKindFilter(key)}
              style={[styles.segmentItem, active && styles.segmentItemActive]}
            >
              <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>

      {loading ? (
        <ActivityIndicator style={styles.loader} color={theme.colors.primary} />
      ) : error ? (
        <Text style={styles.error}>Cannot reach the API ({error}). Is the backend running?</Text>
      ) : (
        <FlatList
          data={rooms}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <RoomCard room={item} onPress={() => navigation.navigate("RoomDetail", { room: item })} />
          )}
          ListEmptyComponent={<Text style={styles.empty}>No open rooms in this filter yet.</Text>}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
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
  matchRow: {
    flexDirection: "row",
    gap: theme.spacing(1.5),
    marginBottom: theme.spacing(2),
  },
  matchButton: {
    flex: 1,
    paddingVertical: theme.spacing(1.5),
    borderRadius: theme.radius,
    alignItems: "center",
  },
  matchPrimary: {
    backgroundColor: theme.colors.primary,
  },
  matchPrimaryText: {
    color: "#FFFFFF",
    fontWeight: "700",
    fontSize: 15,
  },
  matchSecondary: {
    backgroundColor: theme.colors.card,
    borderWidth: 1,
    borderColor: theme.colors.primary,
  },
  matchSecondaryText: {
    color: theme.colors.primary,
    fontWeight: "700",
    fontSize: 15,
  },
  matchDisabled: {
    opacity: 0.6,
  },
  browseLabel: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.muted,
    marginBottom: theme.spacing(1),
  },
  segment: {
    flexDirection: "row",
    backgroundColor: "#E2E8F0",
    borderRadius: 999,
    padding: 3,
    marginBottom: theme.spacing(2),
  },
  segmentItem: {
    flex: 1,
    paddingVertical: theme.spacing(0.75),
    alignItems: "center",
    borderRadius: 999,
  },
  segmentItemActive: {
    backgroundColor: "#FFFFFF",
  },
  segmentText: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.muted,
  },
  segmentTextActive: {
    color: theme.colors.primary,
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
