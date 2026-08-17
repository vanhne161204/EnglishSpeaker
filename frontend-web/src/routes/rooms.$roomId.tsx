import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  assist,
  createNote,
  getRoom,
  joinRoom,
  leaveRoom,
  listMessages,
  listQuestions,
  listTopics,
  moderateRoom,
  roomSocketUrl,
  transcribe,
  translate,
  type Message,
  type ModerationAction,
  type NoteCreate,
  type Room,
  type Topic,
  type TopicQuestion,
} from "@/lib/api";
import { ensureUser, randomGuestName } from "@/lib/identity";
import { LANGS, topicEmoji } from "@/lib/presentation";
import { useAiVoice } from "@/lib/voice/use-ai-voice";
import { useRoomVoice } from "@/lib/voice/use-room-voice";
import { VOICE_FILTERS, voiceFilterLabel, type VoiceFilterId } from "@/lib/voice/voice-mask";
import { AiVoiceCard } from "@/components/room/voice-panel";
import { ErrorState } from "./topics.index";

export const Route = createFileRoute("/rooms/$roomId")({
  head: () => ({
    meta: [
      { title: "Room — EnglishTalker" },
      {
        name: "description",
        content: "Join an English speaking room — live chat, in-room translator, and an AI coach.",
      },
    ],
  }),
  component: RoomPage,
});

type ChatLine =
  | { kind: "message"; id: string; name: string; text: string; mine: boolean }
  | { kind: "system"; id: string; text: string };

function RoomPage() {
  const { roomId } = Route.useParams();
  const roomQ = useQuery({ queryKey: ["room", roomId], queryFn: () => getRoom(roomId) });
  const topicsQ = useQuery({ queryKey: ["topics"], queryFn: () => listTopics() });

  if (roomQ.isLoading) {
    return (
      <section className="container-page py-20">
        <div className="h-40 rounded-4xl bg-card border border-border animate-pulse" />
      </section>
    );
  }
  if (roomQ.isError || !roomQ.data) {
    return (
      <section className="container-page py-20">
        <ErrorState
          message={(roomQ.error as Error)?.message ?? "Room not found"}
          onRetry={() => roomQ.refetch()}
        />
        <div className="mt-6 text-center">
          <Link to="/rooms" className="text-primary hover:underline">
            ← Back to all rooms
          </Link>
        </div>
      </section>
    );
  }

  const room = roomQ.data;
  const topic = topicsQ.data?.find((t) => t.title === room.topic) ?? null;
  return <RoomLive room={room} topic={topic} topicId={topic?.id ?? null} />;
}

/** A member seen via the chat presence channel (besides you). */
interface PresenceMember {
  id: string;
  name: string;
}

function RoomLive({
  room,
  topic,
  topicId,
}: {
  room: Room;
  topic: Topic | null;
  topicId: string | null;
}) {
  const navigate = useNavigate();
  const isIncognito = room.mode === "incognito";
  const [userId, setUserId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string>("You");
  const [joinError, setJoinError] = useState<string | null>(null);
  // Password-protected rooms: gate the join behind a prompt (the owner is exempt).
  const [roomPassword, setRoomPassword] = useState<string | null>(null);
  const [showPasswordPrompt, setShowPasswordPrompt] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [present, setPresent] = useState<PresenceMember[]>([]);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  // Incognito setup: a user must pick an alias + voice filter before entering, so
  // their real name and voice never reach the room (PRD §7.2).
  const [showIncognitoSetup, setShowIncognitoSetup] = useState(isIncognito);
  const [voiceFilter, setVoiceFilter] = useState<VoiceFilterId>("none");
  // Owner's optimistic view of which members they've muted (enforcement is on the target).
  const [mutedIds, setMutedIds] = useState<ReadonlySet<string>>(new Set());
  const socketRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isOwner = userId != null && room.owner_id === userId;

  // Save a sentence to the user's notes (PRD §8.7), with a brief confirmation.
  const saveNote = useCallback(
    async (note: NoteCreate) => {
      try {
        await createNote({ topic: room.topic, ...note });
        setNotice("Saved to your notes ✓");
      } catch (e) {
        setNotice(`Couldn't save note: ${(e as Error).message}`);
      }
      window.setTimeout(() => setNotice(null), 2500);
    },
    [room.topic],
  );

  // Voice call + Voice-with-AI live here (not in a child) so the mic interlock
  // (PRD §8.8) can be enforced across both: a live AI-voice session mutes the
  // room mic and restores it afterwards.
  // Incognito rooms disguise the outbound voice with the user's chosen filter
  // (PRD §7.2); normal rooms keep the real voice ("none").
  const voice = useRoomVoice(room.id, userId, displayName, voiceFilter);
  const ai = useAiVoice(topicId);
  const { suspendMic, resumeMic, setHostMuted, leave: leaveCall } = voice;

  const flashNotice = useCallback((message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 5000);
  }, []);

  // Owner action against a member (PRD §8.3). Enforcement is delivered to the
  // target over the room's chat channel; here we just issue the command.
  const handleModerate = useCallback(
    (targetUserId: string, action: ModerationAction) => {
      if (!userId) return;
      moderateRoom(room.id, { owner_id: userId, target_user_id: targetUserId, action }).catch(
        (err) => flashNotice(`Couldn't ${action} member: ${(err as Error).message}`),
      );
    },
    [userId, room.id, flashNotice],
  );
  useEffect(() => {
    if (ai.active) suspendMic();
    else resumeMic();
  }, [ai.active, suspendMic, resumeMic]);
  useEffect(() => {
    if (!voice.error) return;
    setNotice(voice.error);
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [voice.error]);
  useEffect(() => {
    if (!ai.error) return;
    setNotice(ai.error);
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [ai.error]);

  // 1) Ensure a profile, join the room, then load history.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await ensureUser();
        if (cancelled) return;
        setUserId(user.id);
        // In incognito the alias is set when the user confirms the setup modal, so
        // the real profile name is never used for the room.
        if (!isIncognito) setDisplayName(user.display_name);
        // Locked room: ask for the password before joining (the owner is exempt).
        const isOwnerUser = room.owner_id === user.id;
        if (room.has_password && !isOwnerUser && roomPassword === null) {
          setShowPasswordPrompt(true);
          return;
        }
        await joinRoom(room.id, {
          user_id: user.id,
          password: roomPassword ?? undefined,
        });
        if (cancelled) return;
        setShowPasswordPrompt(false);
        const history = await listMessages(room.id);
        if (cancelled) return;
        setLines(
          history.map((m: Message) => ({
            kind: "message" as const,
            id: m.id,
            name: m.sender_name,
            text: m.text,
            mine: m.user_id === user.id,
          })),
        );
      } catch (err) {
        if (cancelled) return;
        const e = err as { code?: string; message: string };
        // Wrong/missing room password → re-open the prompt with an error.
        if (e.code === "room_password") {
          setRoomPassword(null);
          setPasswordError("Incorrect password. Try again.");
          setShowPasswordPrompt(true);
        } else {
          setJoinError(e.message);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [room.id, isIncognito, roomPassword, room.has_password, room.owner_id]);

  // Adopt the password the user typed, then let the join effect retry with it.
  const confirmPassword = useCallback((pw: string) => {
    setPasswordError(null);
    setRoomPassword(pw);
  }, []);

  // 2) Open the live chat WebSocket once we have an identity — and, for incognito,
  // once the alias has been chosen so the real name is never sent.
  useEffect(() => {
    if (!userId) return;
    if (isIncognito && showIncognitoSetup) return;
    if (showPasswordPrompt) return; // wait until the room password is accepted
    const ws = new WebSocket(roomSocketUrl(room.id, userId, displayName));
    socketRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(event.data as string);
      } catch {
        return;
      }
      if (frame.type === "message" && frame.message) {
        const m = frame.message as Message;
        setLines((prev) =>
          prev.some((l) => l.kind === "message" && l.id === m.id)
            ? prev
            : [
                ...prev,
                {
                  kind: "message",
                  id: m.id,
                  name: m.sender_name,
                  text: m.text,
                  mine: m.user_id === userId,
                },
              ],
        );
      } else if (frame.type === "roster") {
        // Sent once on connect: the members already in the room. Seed the list
        // with everyone except yourself, so people who joined earlier show up.
        const members = Array.isArray(frame.members) ? frame.members : [];
        setPresent(
          members
            .map((m) => ({ id: String(m.user_id ?? ""), name: String(m.name ?? "Someone") }))
            .filter((m) => m.id && m.id !== userId),
        );
      } else if (frame.type === "presence") {
        const pid = String(frame.user_id ?? "");
        const name = String(frame.name ?? "Someone");
        const joined = frame.event === "join";
        if (!pid || pid === userId) return; // Don't list yourself among the others.
        setPresent((prev) =>
          joined
            ? prev.some((p) => p.id === pid)
              ? prev
              : [...prev, { id: pid, name }]
            : prev.filter((p) => p.id !== pid),
        );
        setLines((prev) => [
          ...prev,
          {
            kind: "system",
            id: `sys-${Date.now()}-${Math.random()}`,
            text: `${name} ${joined ? "joined" : "left"} the room.`,
          },
        ]);
      } else if (frame.type === "moderation") {
        const target = String(frame.target ?? "");
        const action = String(frame.action ?? "");
        if (target === userId) {
          // I'm the target — obey the owner's command on this client.
          if (action === "kick") {
            flashNotice("You were removed from this room by the host.");
            leaveCall();
            window.setTimeout(() => void navigate({ to: "/rooms" }), 1200);
          } else if (action === "mute") {
            setHostMuted(true);
            flashNotice("The host muted your microphone.");
          } else if (action === "unmute") {
            setHostMuted(false);
            flashNotice("The host let you speak again.");
          }
        } else if (action === "kick") {
          // Reflect the removal in everyone's member list right away.
          setPresent((prev) => prev.filter((p) => p.id !== target));
        }
      }
    };
    return () => {
      ws.close();
      socketRef.current = null;
    };
  }, [
    userId,
    room.id,
    displayName,
    isIncognito,
    showIncognitoSetup,
    showPasswordPrompt,
    flashNotice,
    leaveCall,
    navigate,
    setHostMuted,
  ]);

  // Auto-scroll chat to the newest line.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  // Leave the room on unmount (best-effort).
  useEffect(() => {
    return () => {
      if (userId) void leaveRoom(room.id, { user_id: userId }).catch(() => {});
    };
  }, [userId, room.id]);

  const send = useCallback((text: string) => {
    const t = text.trim();
    const ws = socketRef.current;
    if (!t || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ text: t }));
    setDraft("");
  }, []);

  const peopleCount = Math.max(room.participant_count, present.length + 1);

  // Owner moderation from the speaker tiles (optimistic mute state + issue command).
  const toggleMemberMute = (id: string) => {
    const muted = mutedIds.has(id);
    setMutedIds((prev) => {
      const next = new Set(prev);
      if (muted) next.delete(id);
      else next.add(id);
      return next;
    });
    handleModerate(id, muted ? "unmute" : "mute");
  };
  const kickMember = (id: string) => handleModerate(id, "kick");

  // Speaker grid: you first, then members on the voice call, then text-only
  // members, then empty seats up to capacity.
  const voiceIds = new Set(voice.members.map((m) => m.id));
  const textOnly = present.filter((p) => !voiceIds.has(p.id));
  const emptySeats = Math.max(0, room.capacity - (1 + voice.members.length + textOnly.length));

  const confirmIncognito = (name: string, filter: VoiceFilterId) => {
    setDisplayName(name);
    setVoiceFilter(filter);
    setShowIncognitoSetup(false);
    setLines((prev) => [
      ...prev,
      {
        kind: "system",
        id: `sys-${Date.now()}-${Math.random()}`,
        text: `You joined incognito as ${name} (voice: ${voiceFilterLabel(filter)}).`,
      },
    ]);
  };

  return (
    <section className="container-page py-6 lg:py-8">
      {showIncognitoSetup && <IncognitoSetupModal onConfirm={confirmIncognito} />}

      {showPasswordPrompt && (
        <RoomPasswordModal onConfirm={confirmPassword} error={passwordError} />
      )}

      {isIncognito && !showIncognitoSetup && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-2 text-xs">
          <span>
            🕶️ Incognito · You appear as <b className="text-foreground">{displayName}</b> · Voice:{" "}
            <b className="text-foreground">{voiceFilterLabel(voiceFilter)}</b>
          </span>
          <button
            onClick={() => setShowIncognitoSetup(true)}
            className="rounded-full border border-border bg-background px-3 py-1 hover:bg-muted"
          >
            Change
          </button>
        </div>
      )}

      {/* Floating quick nav — jumps to the sections below */}
      <div className="fixed right-3 sm:right-5 top-1/2 -translate-y-1/2 z-40 flex flex-col gap-2">
        <QuickNavButton targetId="topic-section" icon="📚" label="Topic" />
        <QuickNavButton targetId="translate-section" icon="🌐" label="Translate" />
        <QuickNavButton targetId="ai-section" icon="🤖" label="AI" />
      </div>

      <div className="mb-3">
        <Link to="/rooms" className="text-xs text-muted-foreground hover:text-foreground">
          ← All rooms
        </Link>
      </div>

      {joinError && (
        <div className="mb-4">
          <ErrorState message={joinError} onRetry={() => window.location.reload()} />
        </div>
      )}

      <div className="grid lg:grid-cols-12 gap-5">
        {/* People stage with merged room info */}
        <div className="lg:col-span-8 rounded-4xl border border-border bg-gradient-to-br from-cream to-card p-5 sm:p-7 min-h-[440px]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                In the room
              </div>
              <h1 className="mt-1 text-xl sm:text-2xl text-ink flex items-center gap-2">
                <span className="text-xl sm:text-2xl">{topicEmoji(room.topic)}</span>
                <span className="truncate">{room.title}</span>
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <Tag>{room.mode}</Tag>
                <Tag>{room.kind === "one_on_one" ? "1-on-1" : "Group"}</Tag>
                {room.level && <Tag>{room.level}</Tag>}
                <span>
                  · {peopleCount}/{room.capacity} seats
                </span>
                <span className="inline-flex items-center gap-1">
                  <span
                    className={`h-2 w-2 rounded-full inline-block ${connected ? "bg-emerald-500" : "bg-muted-foreground/50"}`}
                  />
                  {connected ? "Live" : "Connecting…"}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {isOwner && (
                <span className="rounded-full bg-primary/10 text-primary border border-primary/20 px-3 py-1 text-xs font-semibold">
                  You are host
                </span>
              )}
              {voice.joined ? (
                <button
                  onClick={voice.leave}
                  className="rounded-full bg-destructive text-destructive-foreground px-3 py-1.5 text-xs font-semibold hover:opacity-90"
                >
                  Leave voice
                </button>
              ) : (
                <button
                  onClick={() => void voice.join()}
                  disabled={voice.status === "connecting"}
                  className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-semibold hover:bg-muted disabled:opacity-50"
                >
                  {voice.status === "connecting" ? "Joining…" : "🎙️ Join voice"}
                </button>
              )}
              <Link
                to="/rooms"
                className="rounded-full bg-destructive/90 text-destructive-foreground px-3 py-1.5 text-xs font-semibold"
              >
                Leave
              </Link>
            </div>
          </div>

          {/* Voice controls (shown while on the call) */}
          {voice.joined && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <VoiceToggle
                on={voice.micOn}
                disabled={voice.micSuspended}
                onClick={voice.toggleMic}
                onLabel="🎙️ Mic on"
                offLabel={voice.micSuspended ? "🎙️ Paused for AI" : "🔇 Mic off"}
              />
              <VoiceToggle
                on={voice.speakerOn}
                onClick={voice.toggleSpeaker}
                onLabel="🔊 Speaker on"
                offLabel="🔈 Speaker off"
              />
              {voice.voiceMasked && (
                <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                  🎭 Voice: {voiceFilterLabel(voiceFilter)}
                </span>
              )}
            </div>
          )}

          {/* Topic chip (this room's topic) */}
          {room.topic && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground mr-1">
                Topic:
              </span>
              <button
                onClick={() =>
                  document
                    .getElementById("topic-section")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" })
                }
                className="rounded-full px-2.5 py-1 text-xs border bg-primary text-primary-foreground border-primary"
              >
                {topicEmoji(room.topic)} {room.topic}
              </button>
            </div>
          )}

          {/* Speakers grid */}
          <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-4 sm:gap-5">
            <SpeakerTile
              name={displayName}
              you
              isHost={isOwner}
              speaking={voice.joined && voice.selfSpeaking && voice.micOn && !voice.hostMuted}
              muted={voice.joined && (!voice.micOn || voice.hostMuted)}
            />
            {voice.members.map((m) => (
              <SpeakerTile
                key={m.id}
                name={m.name}
                speaking={m.speaking}
                onCall
                canModerate={isOwner}
                muted={mutedIds.has(m.id)}
                onMute={() => toggleMemberMute(m.id)}
                onKick={() => kickMember(m.id)}
              />
            ))}
            {textOnly.map((p) => (
              <SpeakerTile
                key={p.id}
                name={p.name}
                canModerate={isOwner}
                muted={mutedIds.has(p.id)}
                onMute={() => toggleMemberMute(p.id)}
                onKick={() => kickMember(p.id)}
              />
            ))}
            {Array.from({ length: emptySeats }).map((_, i) => (
              <EmptySeat key={i} />
            ))}
          </div>
        </div>

        {/* Side chat */}
        <aside className="lg:col-span-4 rounded-4xl border border-border bg-card flex flex-col min-h-[440px]">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="text-sm font-semibold">💬 Live chat</div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {lines.filter((l) => l.kind === "message").length} msgs
            </span>
          </div>
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[460px]">
            {lines.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-8">
                No messages yet — say hello! 👋
              </div>
            )}
            {lines.map((l) => (
              <ChatBubble
                key={l.id}
                line={l}
                onSave={
                  l.kind === "message"
                    ? () =>
                        saveNote({
                          improved_text: l.text,
                          source: l.mine ? "self" : "partner",
                        })
                    : undefined
                }
              />
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
            className="border-t border-border p-3 flex items-center gap-2"
          >
            <MicButton
              onTranscript={(t) => {
                setDraft((d) => (d ? `${d} ${t}` : t));
                setNotice("Speech turned into text — edit and send, or save it.");
                window.setTimeout(() => setNotice(null), 2500);
              }}
              onError={(msg) => {
                setNotice(msg);
                window.setTimeout(() => setNotice(null), 5000);
              }}
            />
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={connected ? "Type or speak a message…" : "Connecting to the room…"}
              disabled={!connected}
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:border-primary disabled:opacity-60"
            />
            {draft.trim() && (
              <button
                type="button"
                onClick={() => saveNote({ improved_text: draft.trim(), source: "self" })}
                title="Save this sentence to your notes"
                className="rounded-full border border-border px-3 py-2 text-xs font-semibold hover:bg-muted"
              >
                ＋ Note
              </button>
            )}
            <button
              type="submit"
              disabled={!connected}
              className="rounded-full bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </aside>
      </div>

      {/* Topic detail — questions come from the topic's documentation (PRD §8.2) */}
      <div id="topic-section" className="scroll-mt-24">
        <TopicDetailCard topic={topic} topicId={topicId} onUse={(t) => setDraft(t)} />
      </div>

      {/* Translate + AI */}
      <div className="mt-5 grid lg:grid-cols-2 gap-5 items-start">
        <div id="translate-section" className="scroll-mt-24">
          {/* `saveNote` tags the note with the room's topic automatically. */}
          <TranslateCard onSaveNote={saveNote} />
        </div>
        <div id="ai-section" className="scroll-mt-24 flex flex-col gap-5">
          <AiCoachCard
            topicId={topicId}
            onUse={(text) => setDraft(text)}
            onSave={(original, improved) =>
              saveNote({
                original_text: original || null,
                improved_text: improved,
                source: "ai",
              })
            }
          />
          <AiVoiceCard
            ai={ai}
            micSuspended={voice.micSuspended}
            onSaveNote={(text) => saveNote({ improved_text: text, source: "ai" })}
          />
        </div>
      </div>

      {/* Save / STT confirmation toast */}
      {notice && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background shadow-lg">
          {notice}
        </div>
      )}
    </section>
  );
}

/* ---------- Room layout pieces (new design) ---------- */

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-muted text-muted-foreground px-2 py-0.5 text-[10px] uppercase tracking-wider">
      {children}
    </span>
  );
}

function QuickNavButton({
  targetId,
  icon,
  label,
}: {
  targetId: string;
  icon: string;
  label: string;
}) {
  return (
    <button
      onClick={() =>
        document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" })
      }
      title={label}
      className="group flex flex-col items-center justify-center gap-0.5 h-14 w-14 rounded-2xl border border-border bg-card/95 backdrop-blur shadow-md hover:shadow-lg hover:border-primary/50 hover:bg-primary/5 transition-all"
    >
      <span className="text-xl leading-none">{icon}</span>
      <span className="text-[9px] uppercase tracking-wider font-semibold text-muted-foreground group-hover:text-primary">
        {label}
      </span>
    </button>
  );
}

function VoiceToggle({
  on,
  onClick,
  onLabel,
  offLabel,
  disabled,
}: {
  on: boolean;
  onClick: () => void;
  onLabel: string;
  offLabel: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={on}
      className={`rounded-full px-3 py-1.5 text-xs font-semibold border transition-colors disabled:opacity-60 ${
        on
          ? "bg-primary/10 border-primary/30 text-primary"
          : "bg-muted border-border text-muted-foreground"
      }`}
    >
      {on ? onLabel : offLabel}
    </button>
  );
}

function SpeakerTile({
  name,
  you,
  isHost,
  speaking,
  muted,
  onCall,
  canModerate,
  onMute,
  onKick,
}: {
  name: string;
  you?: boolean;
  isHost?: boolean;
  speaking?: boolean;
  muted?: boolean;
  onCall?: boolean;
  canModerate?: boolean;
  onMute?: () => void;
  onKick?: () => void;
}) {
  const ring = speaking ? "ring-4 ring-primary/40" : "ring-1 ring-border";
  return (
    <div
      className={`rounded-3xl bg-card border border-border p-3 flex flex-col items-center text-center transition-shadow hover:shadow-lg ${speaking ? "shadow-md" : ""}`}
    >
      <div
        className={`relative h-14 w-14 sm:h-16 sm:w-16 rounded-full bg-gradient-to-br from-primary/80 to-secondary text-primary-foreground flex items-center justify-center text-lg font-bold ${ring}`}
      >
        {name.charAt(0).toUpperCase()}
        {muted && (
          <span className="absolute -bottom-0.5 -right-0.5 h-5 w-5 rounded-full bg-destructive text-destructive-foreground text-[10px] flex items-center justify-center border-2 border-card">
            🔇
          </span>
        )}
        {!muted && speaking && (
          <span className="absolute -bottom-0.5 -right-0.5 h-5 w-5 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center border-2 border-card">
            🎙️
          </span>
        )}
      </div>
      <div className="mt-2 font-semibold text-foreground text-sm truncate w-full">
        {name}
        {you ? " (you)" : ""}
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
        {isHost ? (
          <span className="rounded-full bg-primary/15 text-primary px-2 py-0.5">Host</span>
        ) : onCall ? (
          <span>on call</span>
        ) : (
          <span>in room</span>
        )}
      </div>
      {canModerate && !you && (onMute || onKick) && (
        <div className="mt-2 flex items-center gap-1.5 w-full justify-center">
          {onMute && (
            <button
              onClick={onMute}
              title={muted ? "Let this member speak again" : "Mute this member"}
              className="flex-1 rounded-full border border-border bg-background hover:bg-muted px-2 py-1 text-[11px]"
            >
              {muted ? "🔊 Unmute" : "🔇 Mute"}
            </button>
          )}
          {onKick && (
            <button
              onClick={onKick}
              title="Remove from room"
              className="rounded-full border border-destructive/30 bg-destructive/5 text-destructive hover:bg-destructive/10 px-2 py-1 text-[11px]"
            >
              👋
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function EmptySeat() {
  return (
    <div className="rounded-3xl border-2 border-dashed border-border p-4 flex flex-col items-center justify-center text-center min-h-[150px]">
      <div className="h-16 w-16 sm:h-20 sm:w-20 rounded-full border-2 border-dashed border-border flex items-center justify-center text-muted-foreground text-2xl">
        ＋
      </div>
      <div className="mt-3 text-xs text-muted-foreground">Empty seat</div>
    </div>
  );
}

function TopicDetailCard({
  topic,
  topicId,
  onUse,
}: {
  topic: Topic | null;
  topicId: string | null;
  onUse: (text: string) => void;
}) {
  // Questions live in the topic's published documentation (PRD §8.2). Fetching
  // the flat feed keeps this card to a single request, answer templates included.
  const questionsQ = useQuery({
    queryKey: ["questions", topicId],
    queryFn: () => listQuestions(topicId ?? undefined),
    enabled: topicId != null,
  });
  const questions = questionsQ.data ?? [];

  return (
    <div className="mt-5 rounded-4xl border border-border bg-card p-5 sm:p-7">
      <div className="flex items-start gap-4">
        <div className="h-14 w-14 sm:h-16 sm:w-16 rounded-3xl bg-primary/10 flex items-center justify-center text-3xl sm:text-4xl">
          {topicEmoji(topic?.title ?? null)}
        </div>
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Now talking about
          </div>
          <h2 className="text-2xl sm:text-3xl text-ink">{topic?.title ?? "Open conversation"}</h2>
          {topic?.description && (
            <p className="mt-1 text-sm sm:text-base text-muted-foreground">{topic.description}</p>
          )}
          {topic?.level && (
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wider">
              <Tag>{topic.level}</Tag>
              <Tag>Speaking practice</Tag>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-3xl border border-border bg-background/60 p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm font-semibold flex items-center gap-2">
            <span className="h-7 w-7 rounded-full bg-primary text-primary-foreground inline-flex items-center justify-center text-xs">
              ?
            </span>
            Questions to ask
          </div>
          <span className="text-xs text-muted-foreground">
            Tap a line to put it in the chat box
          </span>
        </div>

        {questionsQ.isLoading ? (
          <div className="mt-4 space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded-2xl bg-card border border-border animate-pulse"
              />
            ))}
          </div>
        ) : questions.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            No questions for this topic yet — an admin can add them.
          </p>
        ) : (
          <ol className="mt-4 space-y-2.5">
            {questions.map((q, index) => (
              <QuestionAnswerRow key={q.id} question={q} index={index} onUse={onUse} />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/**
 * One numbered question with its sample answer, side by side.
 *
 * Both halves are buttons: the question is what you *ask* your partner, the
 * answer is a sentence you can *say* — clicking either drops it into the chat
 * box, so a learner who freezes always has something to send (PRD §8.2).
 */
function QuestionAnswerRow({
  question,
  index,
  onUse,
}: {
  question: TopicQuestion;
  index: number;
  onUse: (text: string) => void;
}) {
  const answer = question.answer_templates[0];

  return (
    <li className="rounded-2xl border border-border bg-card p-3 sm:p-4">
      <div className="flex gap-3">
        <span className="flex-none h-6 w-6 rounded-full bg-primary/10 text-primary inline-flex items-center justify-center text-[11px] font-semibold">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1 grid sm:grid-cols-2 gap-2 sm:gap-4">
          <button
            onClick={() => onUse(question.text)}
            title="Ask this question"
            className="text-left group"
          >
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Question
            </div>
            <div className="mt-0.5 text-sm font-medium leading-snug group-hover:text-primary">
              {question.text}
            </div>
            {question.translation && (
              <div className="mt-0.5 text-xs text-muted-foreground italic">
                {question.translation}
              </div>
            )}
          </button>

          {answer ? (
            <button
              onClick={() => onUse(answer.example ?? answer.template)}
              title="Say this answer"
              className="text-left group sm:border-l sm:border-border sm:pl-4"
            >
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Sample answer
              </div>
              <div className="mt-0.5 text-sm leading-snug text-muted-foreground group-hover:text-primary">
                {answer.template}
              </div>
              {answer.example && (
                <div className="mt-0.5 text-xs text-muted-foreground">e.g. {answer.example}</div>
              )}
            </button>
          ) : (
            <div className="sm:border-l sm:border-border sm:pl-4">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Sample answer
              </div>
              <div className="mt-0.5 text-sm text-muted-foreground/60 italic">
                Not added yet — answer in your own words.
              </div>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/* ---------- Incognito setup (display alias + voice filter, PRD §7.2) ---------- */

/** Prompt shown when joining a password-protected room (PRD §8.3). */
function RoomPasswordModal({
  onConfirm,
  error,
}: {
  onConfirm: (password: string) => void;
  error: string | null;
}) {
  const [pw, setPw] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-4xl border border-border bg-card p-6 sm:p-8">
        <h2 className="text-xl text-ink">🔒 This room is locked</h2>
        <p className="mt-1 text-sm text-muted-foreground">Enter the room password to join.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (pw) onConfirm(pw);
          }}
          className="mt-5 space-y-3"
        >
          <input
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            type="password"
            autoFocus
            autoComplete="off"
            placeholder="Room password"
            className="w-full rounded-2xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:border-primary"
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={!pw}
              className="flex-1 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              Join
            </button>
            <Link
              to="/rooms"
              className="rounded-full border border-border bg-background px-5 py-3 text-sm font-semibold text-foreground hover:bg-muted"
            >
              Back
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}

function IncognitoSetupModal({
  onConfirm,
}: {
  onConfirm: (name: string, filter: VoiceFilterId) => void;
}) {
  const [name, setName] = useState(() => randomGuestName());
  const [filter, setFilter] = useState<VoiceFilterId>("none");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="h-12 w-12 rounded-2xl bg-primary/10 inline-flex items-center justify-center text-2xl">
            🕶️
          </div>
          <div className="min-w-0">
            <h2 className="text-xl text-ink">Enter incognito room</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Pick a display name and a voice filter. Your real identity and voice stay hidden from
              others in this room.
            </p>
          </div>
        </div>

        <div className="mt-5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Display name
          </label>
          <div className="mt-1 flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={24}
              placeholder="e.g. QuietPanda42"
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => setName(randomGuestName())}
              className="rounded-full border border-border bg-background px-3 py-2 text-xs hover:bg-muted"
            >
              🎲 Random
            </button>
          </div>
        </div>

        <div className="mt-5">
          <label className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Voice filter
          </label>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
            {VOICE_FILTERS.map((v) => {
              const active = filter === v.id;
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setFilter(v.id)}
                  className={`text-left rounded-2xl border p-3 transition-colors ${
                    active
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background hover:bg-muted"
                  }`}
                >
                  <div className="text-lg">{v.emoji}</div>
                  <div className="text-sm font-semibold">{v.label}</div>
                  <div className="text-[11px] text-muted-foreground leading-snug">{v.desc}</div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between gap-3">
          <Link to="/rooms" className="text-xs text-muted-foreground hover:text-foreground">
            ← Back to rooms
          </Link>
          <button
            type="button"
            disabled={!name.trim()}
            onClick={() => onConfirm(name.trim(), filter)}
            className="rounded-full bg-primary text-primary-foreground px-5 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            Enter room
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Speech-to-text mic (real /transcribe) ---------- */

function MicButton({
  onTranscript,
  onError,
}: {
  onTranscript: (text: string) => void;
  onError: (msg: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const stop = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  const start = async () => {
    // Mic access needs a secure context: HTTPS, or http on localhost/127.0.0.1.
    // Opening the app via a LAN IP over http (e.g. http://192.168.x.x) blocks it.
    if (typeof window !== "undefined" && !window.isSecureContext) {
      onError("Mic needs a secure page. Open the app on http://localhost:8080 (not a LAN IP).");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      onError("This browser blocks microphone access here. Try Chrome/Edge on localhost.");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      onError("Audio recording isn't supported in this browser.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        onError("Microphone permission was blocked. Allow it via the 🔒 icon in the address bar.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        onError("No microphone was found on this device.");
      } else {
        onError(`Couldn't start the microphone${name ? ` (${name})` : ""}.`);
      }
      return;
    }

    try {
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) {
          onError("No audio was captured — try holding the mic a bit longer.");
          return;
        }
        setBusy(true);
        try {
          const res = await transcribe(blob);
          if (res.text.trim()) onTranscript(res.text.trim());
          else onError("Couldn't hear any words. Try again, a little louder.");
        } catch (e) {
          onError(`Transcription failed: ${(e as Error).message}`);
        } finally {
          setBusy(false);
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      onError("Couldn't start recording on this device.");
    }
  };

  return (
    <button
      type="button"
      onClick={recording ? stop : start}
      disabled={busy}
      title={recording ? "Stop and transcribe" : "Speak — turn your voice into text (STT)"}
      aria-label="Speech to text"
      className={`flex-none rounded-full px-3 py-2 text-sm font-semibold disabled:opacity-50 ${
        recording
          ? "bg-destructive text-destructive-foreground animate-pulse"
          : "border border-border hover:bg-muted"
      }`}
    >
      {busy ? "…" : recording ? "■ Stop" : "🎙️"}
    </button>
  );
}

/* ---------- Translate (real /translate) ---------- */

function TranslateCard({ onSaveNote }: { onSaveNote: (note: NoteCreate) => void }) {
  const [from, setFrom] = useState("vi");
  const [to, setTo] = useState("en");
  const [text, setText] = useState("");
  const [out, setOut] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Reset when the pair changes so one click can't save a stale translation twice.
  const [saved, setSaved] = useState(false);

  const swap = () => {
    setFrom(to);
    setTo(from);
    setText(out || text);
    setOut("");
    setProvider(null);
    setSaved(false);
  };

  const run = async () => {
    const t = text.trim();
    if (!t) return;
    setLoading(true);
    setErr(null);
    setSaved(false);
    try {
      const res = await translate({ text: t, source_lang: from, target_lang: to });
      setOut(res.translated_text);
      setProvider(res.provider);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  /** Keep both halves and their languages, so notes can label each side. */
  const savePair = () => {
    onSaveNote({
      original_text: text.trim(),
      translated_text: out,
      source_lang: from,
      target_lang: to,
      source: "translation",
    });
    setSaved(true);
  };

  return (
    <div className="rounded-4xl border border-border bg-card p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-8 w-8 rounded-2xl bg-primary/10 inline-flex items-center justify-center">
            🌐
          </span>
          <div>
            <div className="text-sm font-semibold">Translate</div>
            <div className="text-[11px] text-muted-foreground">
              {provider ? `via ${provider}` : "Quick word & sentence translation"}
            </div>
          </div>
        </div>
        <button
          onClick={swap}
          className="text-xs rounded-full border border-border px-3 py-1 hover:bg-muted"
        >
          ⇄ Swap
        </button>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <LangSelect label="From" value={from} onChange={setFrom} />
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            placeholder="Type a word or sentence…"
            className="mt-2 w-full rounded-2xl border border-border bg-background p-3 text-sm focus:outline-none focus:border-primary resize-none"
          />
        </div>
        <div>
          <LangSelect label="To" value={to} onChange={setTo} />
          <div className="mt-2 w-full min-h-[112px] rounded-2xl border border-border bg-muted/40 p-3 text-sm whitespace-pre-wrap">
            {err ? (
              <span className="text-destructive">{err}</span>
            ) : (
              out || <span className="text-muted-foreground">Translation appears here…</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-end gap-2 flex-wrap">
        {/* Saving the pair builds the learner's own wordbook (PRD §8.7). */}
        {out && !err && (
          <button
            onClick={savePair}
            disabled={saved}
            title="Keep this pair in your notes"
            className="rounded-full border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-60"
          >
            {saved ? "Saved ✓" : "＋ Save to notes"}
          </button>
        )}
        <button
          onClick={run}
          disabled={loading || !text.trim()}
          className="rounded-full bg-primary text-primary-foreground px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Translating…" : "Translate"}
        </button>
      </div>
    </div>
  );
}

function LangSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-full border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ---------- AI coach (real /assist) ---------- */

function AiCoachCard({
  topicId,
  onUse,
  onSave,
}: {
  topicId: string | null;
  onUse: (text: string) => void;
  onSave: (original: string, improved: string) => void;
}) {
  const [improve, setImprove] = useState("");
  const [context, setContext] = useState("");
  const [result, setResult] = useState<{
    suggestion: string;
    provider: string;
    original: string;
  } | null>(null);
  const [loading, setLoading] = useState<"improve" | "reply" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const ask = async (kind: "improve" | "reply") => {
    setErr(null);
    if (kind === "improve" && !improve.trim()) return;
    setLoading(kind);
    try {
      const res = await assist({
        kind,
        text: kind === "improve" ? improve.trim() : "",
        context: kind === "reply" ? context.trim() || null : null,
        topic_id: topicId,
      });
      setResult({
        suggestion: res.suggestion,
        provider: res.provider,
        original: kind === "improve" ? improve.trim() : "",
      });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="rounded-4xl border border-border bg-card p-5 sm:p-6 flex flex-col">
      <div className="flex items-center gap-2">
        <span className="h-8 w-8 rounded-2xl bg-secondary/40 inline-flex items-center justify-center">
          🤖
        </span>
        <div>
          <div className="text-sm font-semibold">AI coach</div>
          <div className="text-[11px] text-muted-foreground">
            Improve a sentence or get a reply idea{topicId ? " · grounded in this topic" : ""}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Improve my sentence
          </span>
          <div className="mt-1 flex gap-2">
            <input
              value={improve}
              onChange={(e) => setImprove(e.target.value)}
              placeholder="e.g. i very like travel"
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => ask("improve")}
              disabled={loading !== null || !improve.trim()}
              className="rounded-full bg-primary text-primary-foreground px-3 py-2 text-xs font-semibold hover:opacity-90 disabled:opacity-50"
            >
              {loading === "improve" ? "…" : "Improve"}
            </button>
          </div>
        </div>
        <div>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            What should I say next?
          </span>
          <div className="mt-1 flex gap-2">
            <input
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="paste the last message (optional)"
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => ask("reply")}
              disabled={loading !== null}
              className="rounded-full border border-border bg-background px-3 py-2 text-xs font-semibold hover:bg-muted disabled:opacity-50"
            >
              {loading === "reply" ? "…" : "Idea"}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-4 flex-1 min-h-[120px] rounded-2xl border border-border bg-background/60 p-4">
        {err ? (
          <span className="text-sm text-destructive">{err}</span>
        ) : result ? (
          <>
            <div className="text-[11px] uppercase tracking-wider text-primary font-semibold">
              Suggestion · {result.provider}
            </div>
            <p className="mt-1 text-sm leading-snug">{result.suggestion}</p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => onUse(result.suggestion)}
                className="rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90"
              >
                Use in chat
              </button>
              <button
                onClick={() => onSave(result.original, result.suggestion)}
                className="rounded-full border border-border px-3 py-1 text-xs font-semibold hover:bg-muted"
              >
                ＋ Save to notes
              </button>
            </div>
          </>
        ) : (
          <span className="text-sm text-muted-foreground">
            Ask the coach to improve a sentence or suggest a reply.
          </span>
        )}
      </div>
    </div>
  );
}

/* ---------- small pieces ---------- */

function ChatBubble({ line, onSave }: { line: ChatLine; onSave?: () => void }) {
  if (line.kind === "system") {
    return <div className="text-center text-[11px] text-muted-foreground italic">{line.text}</div>;
  }
  const me = line.mine;
  return (
    <div className={`group flex ${me ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        {!me && (
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1 ml-3">
            {line.name}
          </div>
        )}
        <div className={`flex items-center gap-1.5 ${me ? "flex-row-reverse" : ""}`}>
          <div
            className={`rounded-2xl px-4 py-2 text-sm leading-snug ${me ? "bg-primary text-primary-foreground rounded-br-md" : "bg-muted text-foreground rounded-bl-md"}`}
          >
            {line.text}
          </div>
          {onSave && (
            <button
              onClick={onSave}
              title="Save to notes"
              aria-label="Save to notes"
              className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-muted-foreground hover:text-primary"
            >
              ＋
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
