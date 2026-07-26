import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import { assist } from "../api/assist";
import { fetchMessages } from "../api/messages";
import { createNote } from "../api/notes";
import { joinRoom, leaveRoom } from "../api/rooms";
import { RoomSocket } from "../api/socket";
import { TranslatorPanel } from "../components/TranslatorPanel";
import { useVoiceRoom } from "../voice/useVoiceRoom";
import { useProfile } from "../context/ProfileContext";
import type { RoomsStackParamList } from "../navigation/RoomsStack";
import type { AssistInput, AssistResult, Message } from "../types";
import { theme } from "../theme";

type ChatRoute = RouteProp<RoomsStackParamList, "RoomChat">;
type Nav = NativeStackNavigationProp<RoomsStackParamList, "RoomChat">;

type Status = "connecting" | "live" | "error";

export function RoomChatScreen() {
  const { room } = useRoute<ChatRoute>().params;
  const navigation = useNavigation<Nav>();
  const { profile } = useProfile();

  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [draft, setDraft] = useState("");
  const [showTranslator, setShowTranslator] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [suggestion, setSuggestion] = useState<AssistResult | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const listRef = useRef<FlatList<Message>>(null);
  const socketRef = useRef<RoomSocket | null>(null);

  // In incognito rooms show a temporary alias instead of the real profile name.
  const alias = useMemo(
    () =>
      room.mode === "incognito"
        ? `Anon-${Math.random().toString(36).slice(2, 6)}`
        : (profile?.display_name ?? "Guest"),
    [room.mode, profile?.display_name],
  );

  const voice = useVoiceRoom(room.id, profile?.id ?? "", alias);

  const onToggleVoice = async () => {
    if (voice.active) {
      voice.leave();
      return;
    }
    try {
      await voice.join();
    } catch {
      Alert.alert(
        "Voice unavailable",
        "Couldn't start voice. It needs microphone access and a development build — voice does not run in Expo Go.",
      );
    }
  };

  useLayoutEffect(() => {
    navigation.setOptions({ title: room.title });
  }, [navigation, room.title]);

  useEffect(() => {
    if (!profile) return;
    let cancelled = false;

    const appendMessage = (message: Message) => {
      setMessages((prev) =>
        prev.some((m) => m.id === message.id) ? prev : [...prev, message],
      );
    };

    (async () => {
      try {
        await joinRoom(room.id, profile.id, alias);
        const history = await fetchMessages(room.id);
        if (cancelled) return;
        setMessages(history);

        const socket = new RoomSocket(room.id, profile.id, alias, {
          onOpen: () => !cancelled && setStatus("live"),
          onEvent: (event) => {
            if (event.type === "message") appendMessage(event.message);
          },
        });
        socket.connect();
        socketRef.current = socket;
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      socketRef.current?.close();
      socketRef.current = null;
      // Best-effort: free the seat when leaving the screen.
      void leaveRoom(room.id, profile.id).catch(() => undefined);
    };
  }, [room.id, room.mode, profile, alias]);

  const send = () => {
    const text = draft.trim();
    if (!text || !socketRef.current) return;
    socketRef.current.send(text);
    setDraft("");
  };

  const requestAssist = async (input: AssistInput) => {
    setAiBusy(true);
    setAiError(null);
    setSuggestion(null);
    try {
      setSuggestion(await assist(input));
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setAiBusy(false);
    }
  };

  const onImprove = () => {
    const text = draft.trim();
    if (text) void requestAssist({ kind: "improve", text });
  };

  const onIdea = () => {
    // Use the most recent message from someone else as context for a reply.
    const lastOther = [...messages].reverse().find((m) => m.user_id !== profile?.id);
    void requestAssist({ kind: "reply", context: lastOther?.text });
  };

  const useSuggestion = () => {
    if (!suggestion) return;
    setDraft(suggestion.suggestion);
    setSuggestion(null);
  };

  const saveSuggestion = async () => {
    if (!suggestion) return;
    try {
      await createNote({
        original_text:
          suggestion.kind === "improve" ? draft.trim() || undefined : undefined,
        improved_text: suggestion.suggestion,
        source: "ai",
        topic: room.topic ?? undefined,
      });
      setSuggestion(null);
      Alert.alert("Saved", "Added to your notes.");
    } catch (err) {
      Alert.alert("Could not save", err instanceof Error ? err.message : "Unknown error");
    }
  };

  const saveMessageToNotes = (message: Message) => {
    Alert.alert("Save to notes?", message.text, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Save",
        onPress: () => {
          void createNote({
            improved_text: message.text,
            source: message.user_id === profile?.id ? "self" : "other",
            topic: room.topic ?? undefined,
          })
            .then(() => Alert.alert("Saved", "Added to your notes."))
            .catch((err) =>
              Alert.alert("Could not save", err instanceof Error ? err.message : "Unknown error"),
            );
        },
      },
    ]);
  };

  if (!profile) return null; // RootNavigator only mounts this with a profile present.

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
    >
      <View style={styles.statusBar}>
        <Text style={styles.statusText}>
          {status === "live"
            ? `● Live · ${room.participant_count}/${room.capacity}`
            : status === "error"
              ? "Disconnected"
              : "Connecting…"}
        </Text>
        {room.mode === "incognito" ? (
          <Text style={styles.aliasText}>You are {alias}</Text>
        ) : null}
      </View>

      <View style={styles.voiceBar}>
        <Pressable
          onPress={() => void onToggleVoice()}
          disabled={voice.connecting}
          style={[styles.voiceButton, voice.active && styles.voiceButtonActive]}
        >
          <Text style={[styles.voiceButtonText, voice.active && styles.voiceButtonTextActive]}>
            {voice.connecting
              ? "Connecting…"
              : voice.active
                ? `📞 Leave voice · ${voice.peers.length + 1} in call`
                : "🎙️ Join voice call"}
          </Text>
        </Pressable>
        {voice.active ? (
          <Pressable
            onPress={voice.toggleMute}
            style={[styles.muteButton, voice.muted && styles.muteButtonActive]}
          >
            <Text style={styles.muteText}>{voice.muted ? "🔇" : "🎤"}</Text>
          </Pressable>
        ) : null}
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <MessageBubble
            message={item}
            mine={item.user_id === profile.id}
            onLongPress={() => saveMessageToNotes(item)}
          />
        )}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          status === "connecting" ? (
            <ActivityIndicator style={styles.loader} color={theme.colors.primary} />
          ) : (
            <Text style={styles.empty}>No messages yet. Say hello! 👋</Text>
          )
        }
      />

      {aiBusy || aiError || suggestion ? (
        <View style={styles.suggestionCard}>
          {aiBusy ? (
            <View style={styles.suggestionBusy}>
              <ActivityIndicator color={theme.colors.primary} />
              <Text style={styles.suggestionLabel}> Coach is thinking…</Text>
            </View>
          ) : aiError ? (
            <Text style={styles.aiError}>Coach unavailable ({aiError}).</Text>
          ) : suggestion ? (
            <>
              <Text style={styles.suggestionLabel}>
                {suggestion.kind === "improve" ? "✨ Try saying" : "💡 Idea"}
                {suggestion.provider === "stub" ? "  ·  demo coach" : ""}
              </Text>
              <Text style={styles.suggestionText}>{suggestion.suggestion}</Text>
              <View style={styles.suggestionActions}>
                <Pressable onPress={useSuggestion} style={styles.suggestionBtn}>
                  <Text style={styles.suggestionBtnText}>Use</Text>
                </Pressable>
                <Pressable onPress={saveSuggestion} style={styles.suggestionBtn}>
                  <Text style={styles.suggestionBtnText}>Save</Text>
                </Pressable>
                <Pressable onPress={() => setSuggestion(null)} style={styles.suggestionBtn}>
                  <Text style={styles.suggestionDismiss}>Dismiss</Text>
                </Pressable>
              </View>
            </>
          ) : null}
        </View>
      ) : null}

      {showTranslator ? <TranslatorPanel /> : null}

      <View style={styles.aiBar}>
        <Pressable
          onPress={onImprove}
          disabled={!draft.trim() || aiBusy}
          style={[styles.aiChip, (!draft.trim() || aiBusy) && styles.aiChipDisabled]}
        >
          <Text style={styles.aiChipText}>✨ Improve my sentence</Text>
        </Pressable>
        <Pressable
          onPress={onIdea}
          disabled={aiBusy}
          style={[styles.aiChip, aiBusy && styles.aiChipDisabled]}
        >
          <Text style={styles.aiChipText}>💡 Idea</Text>
        </Pressable>
      </View>

      <View style={styles.inputRow}>
        <Pressable
          onPress={() => setShowTranslator((v) => !v)}
          style={[styles.translateToggle, showTranslator && styles.translateToggleActive]}
        >
          <Text style={styles.translateIcon}>🌐</Text>
        </Pressable>
        <TextInput
          style={styles.input}
          placeholder="Type a message..."
          placeholderTextColor={theme.colors.muted}
          value={draft}
          onChangeText={setDraft}
          onSubmitEditing={send}
          returnKeyType="send"
        />
        <Pressable onPress={send} disabled={!draft.trim()} style={styles.sendButton}>
          <Text style={styles.sendText}>Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function MessageBubble({
  message,
  mine,
  onLongPress,
}: {
  message: Message;
  mine: boolean;
  onLongPress?: () => void;
}) {
  return (
    <View style={[styles.bubbleRow, mine ? styles.bubbleRowMine : styles.bubbleRowTheirs]}>
      <Pressable
        onLongPress={onLongPress}
        delayLongPress={300}
        style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleTheirs]}
      >
        {!mine ? <Text style={styles.sender}>{message.sender_name}</Text> : null}
        <Text style={[styles.bubbleText, mine && styles.bubbleTextMine]}>{message.text}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  statusBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: theme.spacing(2),
    paddingVertical: theme.spacing(0.75),
    backgroundColor: theme.colors.card,
    borderBottomWidth: 1,
    borderColor: theme.colors.border,
  },
  statusText: {
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.primary,
  },
  aliasText: {
    fontSize: 12,
    color: theme.colors.muted,
  },
  voiceBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing(1),
    paddingHorizontal: theme.spacing(2),
    paddingVertical: theme.spacing(1),
    backgroundColor: theme.colors.card,
    borderBottomWidth: 1,
    borderColor: theme.colors.border,
  },
  voiceButton: {
    flex: 1,
    alignItems: "center",
    paddingVertical: theme.spacing(1),
    borderRadius: 999,
    backgroundColor: "#E0F2FE",
    borderWidth: 1,
    borderColor: "#BAE6FD",
  },
  voiceButtonActive: {
    backgroundColor: "#DCFCE7",
    borderColor: "#86EFAC",
  },
  voiceButtonText: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.primary,
  },
  voiceButtonTextActive: {
    color: "#15803D",
  },
  muteButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.background,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  muteButtonActive: {
    backgroundColor: "#FEE2E2",
    borderColor: "#FCA5A5",
  },
  muteText: {
    fontSize: 18,
  },
  list: {
    padding: theme.spacing(2),
    flexGrow: 1,
  },
  loader: {
    marginTop: theme.spacing(4),
  },
  empty: {
    textAlign: "center",
    marginTop: theme.spacing(4),
    color: theme.colors.muted,
  },
  bubbleRow: {
    marginBottom: theme.spacing(1),
    flexDirection: "row",
  },
  bubbleRowMine: {
    justifyContent: "flex-end",
  },
  bubbleRowTheirs: {
    justifyContent: "flex-start",
  },
  bubble: {
    maxWidth: "80%",
    borderRadius: 14,
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(1),
  },
  bubbleMine: {
    backgroundColor: theme.colors.primary,
    borderBottomRightRadius: 4,
  },
  bubbleTheirs: {
    backgroundColor: theme.colors.card,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderBottomLeftRadius: 4,
  },
  sender: {
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.primary,
    marginBottom: 2,
  },
  bubbleText: {
    fontSize: 15,
    color: theme.colors.text,
  },
  bubbleTextMine: {
    color: "#FFFFFF",
  },
  suggestionCard: {
    backgroundColor: "#EFF6FF",
    borderTopWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: theme.spacing(2),
    paddingVertical: theme.spacing(1.5),
  },
  suggestionBusy: {
    flexDirection: "row",
    alignItems: "center",
  },
  suggestionLabel: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.primary,
  },
  suggestionText: {
    fontSize: 15,
    color: theme.colors.text,
    marginTop: theme.spacing(0.5),
  },
  suggestionActions: {
    flexDirection: "row",
    gap: theme.spacing(1),
    marginTop: theme.spacing(1),
  },
  suggestionBtn: {
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(0.5),
    borderRadius: 999,
    backgroundColor: theme.colors.card,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  suggestionBtnText: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.primary,
  },
  suggestionDismiss: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.muted,
  },
  aiError: {
    color: theme.colors.danger,
    fontSize: 13,
  },
  aiBar: {
    flexDirection: "row",
    gap: theme.spacing(1),
    paddingHorizontal: theme.spacing(1),
    paddingTop: theme.spacing(1),
    backgroundColor: theme.colors.card,
  },
  aiChip: {
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(0.75),
    borderRadius: 999,
    backgroundColor: "#E0F2FE",
    borderWidth: 1,
    borderColor: "#BAE6FD",
  },
  aiChipDisabled: {
    opacity: 0.5,
  },
  aiChipText: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.primary,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    padding: theme.spacing(1),
    gap: theme.spacing(1),
    backgroundColor: theme.colors.card,
    borderTopWidth: 1,
    borderColor: theme.colors.border,
  },
  translateToggle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.background,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  translateToggleActive: {
    backgroundColor: "#E0F2FE",
    borderColor: theme.colors.primary,
  },
  translateIcon: {
    fontSize: 18,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(1),
    fontSize: 15,
    color: theme.colors.text,
    backgroundColor: theme.colors.background,
  },
  sendButton: {
    paddingHorizontal: theme.spacing(1.5),
    paddingVertical: theme.spacing(1),
  },
  sendText: {
    color: theme.colors.primary,
    fontWeight: "700",
    fontSize: 15,
  },
});
