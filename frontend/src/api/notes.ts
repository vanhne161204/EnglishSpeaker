import { apiClient } from "./client";
import type { NoteInput, SentenceNote } from "../types";

export function fetchNotes(): Promise<SentenceNote[]> {
  return apiClient.get<SentenceNote[]>("/notes");
}

export function createNote(input: NoteInput): Promise<SentenceNote> {
  return apiClient.post<SentenceNote>("/notes", input);
}
