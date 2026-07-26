import { apiClient } from "./client";
import type { TranslateInput, TranslateResult } from "../types";

export function translate(input: TranslateInput): Promise<TranslateResult> {
  return apiClient.post<TranslateResult>("/translate", input);
}
