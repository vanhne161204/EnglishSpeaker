// Room side panels (PRD §8.3 rooms/voice + §8.8 Voice With AI).
//
// `RoomInfoPanel` is the single consolidated panel that merges what used to be
// three separate blocks: the room details (topic / people / level), the "in the
// room" member list, and the "voice call" controls. It shows all of it at once.
//
// `AiVoiceCard` renders the separate Voice-With-AI surface. Both take an already
// constructed hook result as a prop: the room page owns `useRoomVoice` and
// `useAiVoice` so the mic interlock (a live AI-voice session mutes the room mic)
// can be enforced across both from one place.

import { useState } from "react";

import type { ModerationAction, Room } from "@/lib/api";
import { levelLabel, modeLabel, sizeLabel, topicEmoji } from "@/lib/presentation";
import type { useAiVoice } from "@/lib/voice/use-ai-voice";
import type { useRoomVoice } from "@/lib/voice/use-room-voice";

/** A member present via text chat (besides you), identified for moderation. */
export interface PresentMember {
  readonly id: string;
  readonly name: string;
}

export interface RoomInfoPanelProps {
  readonly room: Room;
  /** People in the room (max of server count and who we can currently see). */
  readonly peopleCount: number;
  /** Whether the text-chat socket is connected (drives the "Live" status). */
  readonly connected: boolean;
  /** Members present via text chat, besides you. */
  readonly present: readonly PresentMember[];
  readonly displayName: string;
  readonly voice: ReturnType<typeof useRoomVoice>;
  /** True when the current user owns this room and may moderate members (§8.3). */
  readonly isOwner: boolean;
  /** Owner action against a member; no-op for non-owners. */
  readonly onModerate: (targetUserId: string, action: ModerationAction) => void;
}

/**
 * One panel showing everything about the room: details, members, and the voice
 * call controls. Members on the voice call show live speaking / muted state;
 * people present only in text chat are listed as "in room".
 */
export function RoomInfoPanel({
  room,
  peopleCount,
  connected,
  present,
  displayName,
  voice,
  isOwner,
  onModerate,
}: RoomInfoPanelProps) {
  const {
    status,
    joined,
    members,
    micOn,
    speakerOn,
    voiceMasked,
    micSuspended,
    hostMuted,
    selfSpeaking,
  } = voice;
  // The mic is live only when the user wants it on and nothing is forcing it off.
  const micEffectivelyOn = micOn && !micSuspended && !hostMuted;

  // Owner's optimistic view of which members they've muted, so the button can
  // toggle between "Turn off" and "Turn on" (enforcement lives on the member's client).
  const [mutedIds, setMutedIds] = useState<ReadonlySet<string>>(new Set());
  const moderate = (targetUserId: string, action: ModerationAction) => {
    if (action === "kick") {
      onModerate(targetUserId, action);
      return;
    }
    setMutedIds((prev) => {
      const next = new Set(prev);
      if (action === "mute") next.add(targetUserId);
      else next.delete(targetUserId);
      return next;
    });
    onModerate(targetUserId, action);
  };
  const ownerActions = (targetUserId: string) =>
    isOwner
      ? {
          muted: mutedIds.has(targetUserId),
          onToggleMute: () =>
            moderate(targetUserId, mutedIds.has(targetUserId) ? "unmute" : "mute"),
          onKick: () => moderate(targetUserId, "kick"),
        }
      : undefined;

  // De-duplicate: anyone on the voice call is shown from `members`; the rest of
  // the text-chat presence is listed separately so a member never appears twice.
  const voiceIds = new Set(members.map((m) => m.id));
  const textOnly = present.filter((p) => !voiceIds.has(p.id));

  return (
    <div className="rounded-4xl border border-border bg-gradient-to-br from-cream to-card p-5 sm:p-6 flex flex-col">
      {/* Room details */}
      <div className="flex items-start gap-3">
        <span className="text-3xl leading-none">{topicEmoji(room.topic)}</span>
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Room</div>
          <div className="text-lg text-ink truncate">{room.topic ?? "Open conversation"}</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Tag>{modeLabel(room.mode)}</Tag>
        <Tag>{sizeLabel(room.kind)}</Tag>
        <Tag>{levelLabel(room.level)}</Tag>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {peopleCount}/{room.capacity} {peopleCount === 1 ? "person" : "people"}
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className={`h-2 w-2 rounded-full inline-block ${connected ? "bg-emerald-500" : "bg-muted-foreground/50"}`}
          />
          {connected ? "Live" : "Connecting…"}
        </span>
      </div>

      {/* Voice call */}
      <div className="mt-5 border-t border-border pt-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="h-8 w-8 rounded-2xl bg-primary/10 inline-flex items-center justify-center">
              🔊
            </span>
            <div>
              <div className="text-sm font-semibold">Voice call</div>
              <div className="text-[11px] text-muted-foreground">
                {status === "connected"
                  ? `${members.length + 1} on the call`
                  : status === "connecting"
                    ? "Connecting…"
                    : "Talk to members by voice"}
              </div>
            </div>
          </div>
          {joined ? (
            <button
              onClick={voice.leave}
              className="rounded-full bg-destructive text-destructive-foreground px-3 py-1.5 text-xs font-semibold hover:opacity-90"
            >
              Leave call
            </button>
          ) : (
            <button
              onClick={() => void voice.join()}
              disabled={status === "connecting"}
              className="rounded-full bg-primary text-primary-foreground px-3 py-1.5 text-xs font-semibold hover:opacity-90 disabled:opacity-50"
            >
              {status === "connecting" ? "Joining…" : "Join call"}
            </button>
          )}
        </div>

        {joined && (
          <div className="mt-3 flex gap-2">
            <ToggleButton
              on={micOn}
              disabled={micSuspended}
              onClick={voice.toggleMic}
              onLabel="🎙️ Mic on"
              offLabel={micSuspended ? "🎙️ Paused for AI" : "🔇 Mic off"}
              title={
                micSuspended
                  ? "Muted while you talk to the AI — it comes back when you finish"
                  : micOn
                    ? "Mute your microphone"
                    : "Unmute your microphone"
              }
            />
            <ToggleButton
              on={speakerOn}
              onClick={voice.toggleSpeaker}
              onLabel="🔊 Speaker on"
              offLabel="🔈 Speaker off"
              title={speakerOn ? "Stop hearing other members" : "Hear other members"}
            />
          </div>
        )}

        {joined && voiceMasked && (
          <div
            className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground"
            title="Your real voice is disguised so other members can't recognize you (incognito)."
          >
            <span>🎭</span>
            <span>Voice disguised for incognito — others can't recognize you.</span>
          </div>
        )}
      </div>

      {/* Members */}
      <div className="mt-5 border-t border-border pt-4">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          In the room
        </div>
        <ul className="mt-3 space-y-2">
          <MemberRow
            name={displayName}
            you
            speaking={joined && selfSpeaking && micOn && !hostMuted}
            muted={joined && (!micOn || hostMuted)}
            note={hostMuted ? "muted by host" : joined ? undefined : "in room"}
          />
          {members.map((m) => (
            <MemberRow
              key={m.id}
              name={m.name}
              speaking={m.speaking}
              note="on call"
              moderation={ownerActions(m.id)}
            />
          ))}
          {textOnly.map((p) => (
            <MemberRow key={p.id} name={p.name} note="in room" moderation={ownerActions(p.id)} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-muted text-muted-foreground px-2 py-0.5 text-[10px] uppercase tracking-wider">
      {children}
    </span>
  );
}

interface MemberModeration {
  /** Whether the owner has muted this member (drives the toggle label). */
  readonly muted: boolean;
  readonly onToggleMute: () => void;
  readonly onKick: () => void;
}

function MemberRow({
  name,
  speaking,
  muted,
  note,
  you,
  moderation,
}: {
  name: string;
  speaking?: boolean;
  muted?: boolean;
  /** Small right-side status when not speaking/muted, e.g. "on call" or "in room". */
  note?: string;
  you?: boolean;
  /** Owner controls shown for other members; absent for non-owners and yourself. */
  moderation?: MemberModeration;
}) {
  return (
    <li className="flex items-center gap-3 rounded-2xl border border-border bg-card px-3 py-2">
      <span
        className={`h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold text-primary-foreground ${
          you ? "bg-primary" : "bg-gradient-to-br from-primary/80 to-secondary"
        } ${speaking ? "ring-2 ring-emerald-400 ring-offset-1 ring-offset-card" : ""}`}
      >
        {name.charAt(0).toUpperCase()}
      </span>
      <span className="text-sm text-foreground truncate flex-1">
        {name}
        {you ? " (you)" : ""}
      </span>

      {moderation ? (
        <div className="flex items-center gap-1.5">
          <button
            onClick={moderation.onToggleMute}
            title={moderation.muted ? "Let this member speak again" : "Mute this member"}
            aria-label={moderation.muted ? "Unmute member" : "Mute member"}
            className={`rounded-full border px-2 py-1 text-xs font-semibold transition-colors ${
              moderation.muted
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border hover:bg-muted"
            }`}
          >
            {moderation.muted ? "🎙️ On" : "🔇 Off"}
          </button>
          <button
            onClick={moderation.onKick}
            title="Remove this member from the room"
            aria-label="Remove member"
            className="rounded-full border border-destructive/40 text-destructive px-2 py-1 text-xs font-semibold hover:bg-destructive/10"
          >
            Kick
          </button>
        </div>
      ) : muted ? (
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">muted</span>
      ) : speaking ? (
        <span className="text-[10px] uppercase tracking-wider text-emerald-600">speaking</span>
      ) : note ? (
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{note}</span>
      ) : null}
    </li>
  );
}

/* ---------- Voice with AI (STT → assist → TTS) ---------- */

export function AiVoiceCard({
  ai,
  micSuspended,
  onSaveNote,
}: {
  ai: ReturnType<typeof useAiVoice>;
  micSuspended: boolean;
  onSaveNote: (text: string) => void;
}) {
  const phaseLabel: Record<typeof ai.phase, string> = {
    idle: "Ready",
    listening: "Listening…",
    thinking: "Thinking…",
    speaking: "Speaking…",
  };

  return (
    <div className="rounded-4xl border border-border bg-card p-5 sm:p-6 flex flex-col">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="h-8 w-8 rounded-2xl bg-secondary/40 inline-flex items-center justify-center">
            🗣️
          </span>
          <div>
            <div className="text-sm font-semibold">Voice with AI</div>
            <div className="text-[11px] text-muted-foreground">
              {ai.supported ? "Speak with the AI coach" : "Not available in this browser"}
            </div>
          </div>
        </div>
        {ai.supported &&
          (ai.active ? (
            <button
              onClick={ai.stop}
              className="rounded-full bg-destructive text-destructive-foreground px-3 py-1.5 text-xs font-semibold hover:opacity-90"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={ai.start}
              className="rounded-full bg-primary text-primary-foreground px-3 py-1.5 text-xs font-semibold hover:opacity-90"
            >
              Start talking
            </button>
          ))}
      </div>

      {ai.active && (
        <div className="mt-3 flex items-center gap-2 text-[11px]">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 text-primary px-2.5 py-1 font-semibold">
            <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
            {phaseLabel[ai.phase]}
          </span>
          {micSuspended && (
            <span className="text-muted-foreground">Room mic paused so members can't hear.</span>
          )}
        </div>
      )}

      <div className="mt-4 flex-1 min-h-[140px] max-h-[240px] overflow-y-auto rounded-2xl border border-border bg-background/60 p-3 space-y-2">
        {ai.transcript.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {ai.supported
              ? "Tap “Start talking”, then speak. The AI listens, replies, and reads it back."
              : "Voice with AI needs Chrome or Edge. You can still chat with the AI coach by text."}
          </p>
        ) : (
          ai.transcript.map((turn, index) => (
            <TranscriptLine key={index} role={turn.role} text={turn.text} onSave={onSaveNote} />
          ))
        )}
      </div>
    </div>
  );
}

function TranscriptLine({
  role,
  text,
  onSave,
}: {
  role: "user" | "ai";
  text: string;
  onSave: (text: string) => void;
}) {
  const isAi = role === "ai";
  return (
    <div className={`group flex ${isAi ? "justify-start" : "justify-end"}`}>
      <div className="flex items-center gap-1.5 max-w-[90%]">
        <div
          className={`rounded-2xl px-3 py-1.5 text-sm leading-snug ${
            isAi ? "bg-secondary/30 text-foreground" : "bg-primary text-primary-foreground"
          }`}
        >
          {text}
        </div>
        {isAi && (
          <button
            onClick={() => onSave(text)}
            title="Save to notes"
            aria-label="Save to notes"
            className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-muted-foreground hover:text-primary"
          >
            ＋
          </button>
        )}
      </div>
    </div>
  );
}

/* ---------- shared ---------- */

function ToggleButton({
  on,
  onClick,
  onLabel,
  offLabel,
  title,
  disabled,
}: {
  on: boolean;
  onClick: () => void;
  onLabel: string;
  offLabel: string;
  title: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={on}
      className={`flex-1 rounded-full px-3 py-2 text-xs font-semibold border transition-colors disabled:opacity-60 ${
        on
          ? "bg-primary/10 border-primary/30 text-primary"
          : "bg-muted border-border text-muted-foreground"
      }`}
    >
      {on ? onLabel : offLabel}
    </button>
  );
}
