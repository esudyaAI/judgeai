// Domain types for the cabinet UI.
// Mapping to the backend (judgeai/judgeai, src/db/models.py):
//   CaseSummary  ~ Chat
//   CaseFile     ~ Attachment
//   CaseAnalysis ~ Message.analysis (assistant message) — shape not yet agreed with backend.

export type CaseStatus = 'ready' | 'busy' | 'draft' | 'failed';
export type CaseGroup = 'Сегодня' | 'Вчера' | 'Ранее';

export interface CaseSummary {
  id: string;
  title: string;
  group: CaseGroup;
  status: CaseStatus;
  pinned?: boolean;
  /** Secondary line in the sidebar, e.g. "8 окт. · проект готов". */
  meta: string;
}

export type FileExt = 'PDF' | 'DOC' | 'JPG' | 'TXT';

export interface CaseFile {
  name: string;
  ext: FileExt;
  pages: number;
  /** "partial" = some document content could not be read; OCR is not implied. */
  recognition: 'pending' | 'ok' | 'partial' | 'empty' | 'error' | 'unsupported';
}

/** All terms are in months; the scale is drawn from 0 to sanctionMaxMonths. */
export interface SentenceScale {
  sanctionMaxMonths: number;
  /** Upper limit after mitigating rules (e.g. ч. 1 ст. 62 УК РФ). */
  limitMonths: number | null;
  limitNorm: string | null;
  practiceMonths: [from: number, to: number] | null;
  avgSimilarMonths: number | null;
  recommendedMonths: number | null;
  withinSanction: boolean | null;
  extraNotes: string[];
}

export interface PunishmentVariant {
  label: string;
  title: string;
  details: string;
  rationale: string;
}

export interface SimilarVerdict {
  punishment: string;
  court: string;
  match: string;
  /** 0–100 */
  score: number;
}

/** A comparable precedent from the practice base (wire field names; no fabula). */
export interface PrecedentMatch {
  card_id: number;
  court_name: string | null;
  decision_date: string | null;
  uid: string | null;
  source_url: string | null;
  qualifications: string[];
  punishment_months: number | null;
  conditional: boolean;
  recidivism: string | null;
  /** 0–1 */
  score: number;
  breakdown: Record<string, { score: number; weight: number }>;
  filters: { name: string; state: 'passed' | 'failed' | 'uncertain'; reason: string; action: string }[];
  channels: string[];
}

/** Terms of the comparable precedents and the draft's place among them (T28). */
export interface PracticeComparison {
  total: number;
  with_term: number;
  enough_data: boolean;
  min_months: number | null;
  p25_months: number | null;
  median_months: number | null;
  p75_months: number | null;
  max_months: number | null;
  conditional_share: number | null;
  art64_share: number | null;
  art73_share: number | null;
  draft_months: number | null;
  draft_percentile: number | null;
  position: 'below' | 'within' | 'above' | null;
  candidates: number;
  excluded: number;
  vector_used: boolean;
}

export type PrecedentSource = 'cards' | 'text' | 'none' | null;

export interface LegalCheck {
  norm: string;
  status: 'ok' | 'possible_violation' | 'insufficient_data';
  explanation: string;
  source: string;
  value: string | null;
  evidence: string[];
  needs_legal_review: boolean;
}

export interface CaseAnalysis {
  warnings?: string[];
  legalChecks?: LegalCheck[];
  stats: { documents: number; pages: number; seconds: number };
  prompt: string;
  fabula: string;
  qualification: { article: string; title: string } | null;
  draft: { filename: string; note: string } | null;
  scale: SentenceScale | null;
  mitigating: { name: string; norm: string }[];
  aggravating: string;
  personality: string;
  variants: PunishmentVariant[];
  similar: SimilarVerdict[];
  precedentSource?: PrecedentSource;
  precedents?: PrecedentMatch[];
  practice?: PracticeComparison | null;
}

export interface AnalysisStep {
  label: string;
}
