export type QuoteLine = {
  product_id: string;
  name: string;
  description: string;
  unit: string;
  quantity: number;
  unit_price: number;
  list_unit_price: number;
  monthly: number;
  setup_total: number;
  install_days: number;
};

export type Quote = {
  lines: QuoteLine[];
  monthly_subtotal: number;
  list_monthly_subtotal: number;
  monthly_saving: number;
  gst_rate: number;
  monthly_gst: number;
  monthly_total: number;
  one_time_setup: number;
  one_time_gst: number;
  one_time_total: number;
  pay_now: number;
  contract_months: number;
  contract_options: { months: number; monthly_subtotal: number }[];
  expected_activation_days: number;
  valid: boolean;
  violations: { product_id: string; code: string; message: string }[];
};

export type Item = {
  product_id: string;
  name: string;
  unit: string;
  quantity: number;
  reason: string;
  asked: boolean;
  monthly: number;
  setup: number;
  contract_months_if_added: number | null;
};

export type Unavailable = {
  product_id: string;
  name: string;
  asked: boolean;
  reason: string;
  alternative_id: string | null;
  alternative_name: string | null;
};

export type Recommendation = {
  segment: string;
  city_tier: number;
  coverage_confirmed: boolean;
  has_active_gstin: boolean;
  gstin_status: string | null;
  bundle: Item[];
  addons: Item[];
  unavailable: Unavailable[];
  quote: Quote;
  within_budget: boolean | null;
  monthly_difference_vs_current: number | null;
  notes: string[];
};

export type AdvisorReply = {
  session_id: string;
  reply: string;
  mode: "ai" | "guided";
  quick_replies: { label: string; value: string }[];
  multi_select: boolean;
  expects: string | null;
  recommendation: Recommendation | null;
  offer_person: boolean;
};

export type DocumentView = {
  slot: string;
  name: string;
  readable: boolean;
  detected_type: string | null;
  fields: Record<string, string>;
};

export type Check = { code: string; outcome: string; document: string | null; message: string };

export type KycResult = {
  verdict: string;
  checks: Check[];
  verified_fields: Record<string, string>;
};

export type Requirement = { slot: string; state: "uploaded" | "resolved" | "optional" | "needed"; message: string | null };

export type OrderView = {
  id: string;
  language: string;
  current_stage: string;
  under_review: boolean;
  is_live: boolean;
  next_stage: string | null;
  next_stage_on: string | null;
  live_on: string;
  stages: { key: string; state: "done" | "current" | "pending"; on: string }[];
  services: { name: string; quantity: number; live_on: string; is_live: boolean }[];
  updates: { stage: string; on: string }[];
  monthly_total: number;
  pay_now: number;
  contract_months: number;
};

export type QueueLead = {
  lead_id: string;
  business: string;
  contact: string;
  segment: string | null;
  city: string;
  language: string;
  source: string;
  stage: string;
  drop_reason: string;
  score: number | null;
  reasons: string[];
  owner: string;
  next_action: string;
  live: boolean;
};

type ScoreTest = { test_splits: number; auc: number; top_20pct_share_of_activations: number; top_20pct_rate: number; base_rate: number };

export type QueueView = {
  total: number;
  live: number;
  no_contact: number;
  by_owner: Record<string, number>;
  model: ScoreTest;
  chat_model: ScoreTest;
  leads: QueueLead[];
};

export class ApiError extends Error {}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function post<T>(path: string, body: unknown = {}): Promise<T> {
  return fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((response) => handle<T>(response));
}

export function get<T>(path: string): Promise<T> {
  return fetch(`/api${path}`, { cache: "no-store" }).then((response) => handle<T>(response));
}

export function erase(path: string): Promise<void> {
  return fetch(`/api${path}`, { method: "DELETE" }).then((response) => handle<void>(response));
}

export function upload<T>(path: string, slot: string, file: File): Promise<T> {
  const form = new FormData();
  form.set("slot", slot);
  form.set("file", file);
  return fetch(`/api${path}`, { method: "POST", body: form }).then((response) => handle<T>(response));
}

export const rupees = (amount: number) => `₹${Math.round(amount).toLocaleString("en-IN")}`;
