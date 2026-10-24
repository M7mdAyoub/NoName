export type ResultRow = { id:string; parent_id:string|null; level_name:string; code:string|null; statement:string; sort_order:number };
export type IndicatorRow = { id:string; result_id:string|null; code:string|null; name:string; unit:string|null; kind:string|null; baseline:number|null; target:number|null; frequency:string|null; data_source:string|null; status:'draft'|'published' };
export type FieldType = 'text'|'integer'|'decimal'|'select_one'|'select_multiple'|'date';
export type FormField = { id:string; type:FieldType; label:string; required:boolean; options:{value:string;label:string}[]; unit?:string|null; constraints?:{min?:number|null;max?:number|null}|null; pii?:boolean; qualitative?:boolean; section?:string|null };
/** Where a form came from: taken from an uploaded document, proposed by the AI, or built by hand. */
export type FormOrigin = 'document'|'ai'|'manual';
export type FormSchema = { schema_version:1; title:string; entity_key_field?:string|null; fields:FormField[]; origin?:FormOrigin|null; source?:string|null };
export type FormRow = { id:string; key:string; title:string; schema:FormSchema; status:'draft'|'published' };
export type FormSummary = { key:string; title:string; status:'draft'|'published'; submissions:number };
export type DefinitionRow = { id:string; indicator_id:string; definition:Record<string,unknown>; status:string; valid?:boolean; errors?:string[] };
export type QuestionRow = { id:string; indicator_id:string|null; question:string; answer:string|null };
export type Draft = { results:ResultRow[]; indicators:IndicatorRow[]; forms:FormRow[]; definitions:DefinitionRow[]; open_questions:QuestionRow[] };
/** KPI tracking status computed by the server from progress against the target. */
export type Track = 'achieved'|'in_progress'|'not_started'|'no_target'|'not_computable';
export type FeedingForm = { key:string; title:string; submissions:number; origin:FormOrigin|null };
export type DashboardIndicator = { indicator_id:string; code:string|null; name:string; result:Omit<ResultRow,'parent_id'|'sort_order'>|null; kind:string|null; unit:string|null; frequency:string|null; data_source:string|null; baseline:number|null; target:number|null; actual:number|null; progress_pct:number|null; track:Track; forms:FeedingForm[]; status:string; reason:string|null; records:number; components:Record<string,unknown>|null; breakdowns:{dimension:string;label:string;values:{label?:string;value?:string;actual:number|null;status?:string;reason?:string|null;records?:number}[]}[] };
export type DashboardSummary = Record<'total'|Track, number>;
export type Dashboard = {published:boolean;results:ResultRow[];summary:DashboardSummary;indicators:DashboardIndicator[];submissions:Record<string,number>};
export type UploadRow = {id:string;status:string;error:string|null;files:{filename:string;size_bytes:number}[];parsed:{filename:string;stats:Record<string,number>;warnings:string[]}[];extraction?:{mode?:string;model?:string;counts?:Record<string,number>;problems?:unknown[]}|null;ir?:{files:unknown[]}|null;created_at?:string;updated_at?:string};
export type SubmissionReceipt = {id:string;form:string;entity_key:string|null;collected_at:string;data:Record<string,unknown>};
export type PublishResult = {published:boolean;forms:number;indicators:number;definitions:number;unanswered_questions:number;without_definition:string[]};
export type Qualitative = {fields:{form:string;field:string;label:string;answers:number;analysed:number;themes:{name:string;description:string;count:number;share_pct:number;quotes:string[]}[];unthemed:number;error:string|null}[];llm:{mode?:string;model?:string}};
export type FieldError={field:string;message:string};
