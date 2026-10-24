// Pure helpers of the form builder (no React, no API): ids, options, cleaning, validation, preview grouping.
// The validation rules mirror the server's validate_form (app/schemas/form.py), with Arabic messages.
import type {FieldType,FormField,FormSchema} from './types';
import {formsInDefinition} from './model';

/** Same pattern as the server: field ids are what calculation rules and answers refer to. */
export const FIELD_ID=/^[a-z][a-z0-9_]{0,62}$/;
export const isSelect=(type:FieldType)=>type==='select_one'||type==='select_multiple';
export const isNumeric=(type:FieldType)=>type==='integer'||type==='decimal';
/** Types that can identify who or what a record is about (server: entity_key_field). */
export const isKeyType=(type:FieldType)=>type==='text'||type==='integer';

/** A question being edited: the saved field plus state only the builder needs (stripped by cleanSchema). */
export type BuilderField=FormField&{
 /** Stable React key: the id of a new question can still change. */
 uid:string;
 /** Added in this session and not saved yet: only then may its id change. */
 fresh?:boolean;
 /** The id still follows the label (the person has not typed one). */
 autoId?:boolean;
 /** The options text as typed, one option per line. */
 optionsText?:string;
};
export type BuilderSchema=Omit<FormSchema,'fields'>&{
 fields:BuilderField[];
 /** Ids a new question never takes automatically: those of saved questions (even once removed here) and
  * those calculation rules read. Otherwise a rule reading a removed question would silently read the new one. */
 reserved?:string[];
 /** The uid of the identifier question (entity_key_field). While a new question's id is being typed it can
  * equal the identifier's id for a moment; the uid says which of the two questions the identifier is. */
 entityUid?:string|null;
};
export type SchemaIssue={field:number|null;part:'title'|'fields'|'entity'|'id'|'label'|'options'|'constraints';message:string};
type Option={value:string;label:string};
type SchemaLike=Pick<FormSchema,'title'|'entity_key_field'|'origin'|'source'>&{fields:FormField[]};

let sequence=0;
/** A new React key for a question (made outside state updaters, which React may call twice). */
export const nextUid=()=>`field-${++sequence}`;

/** Latin letters and digits of a text, lower-cased and joined by "_". Empty for an all-Arabic text. */
export function slug(text:string,limit=40):string{
 return text.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_+/,'').slice(0,limit).replace(/_+$/,'');
}

/** A valid, unused field id for a label: a slug of its Latin letters/digits, else q_1, q_2 … */
export function newFieldId(label:string,taken:Iterable<string>):string{
 const used=new Set(taken);
 let base=slug(label);
 if(!base){let n=1;while(used.has(`q_${n}`))n++;return `q_${n}`;}
 if(!/^[a-z]/.test(base))base=`q_${base}`;
 let id=base;
 for(let n=2;used.has(id);n++)id=`${base.slice(0,36)}_${n}`;
 return id;
}

/** One option per non-empty line. An unchanged label keeps its earlier value (from `previous`, first match
 * wins, each used once); a new label gets a slug of its Latin letters/digits, else opt_1, opt_2 …, never a
 * value found in `previous`: a rule reading the value of a removed or renamed option would otherwise
 * silently count the new answer (and the builder could not warn that the value is gone).
 * Values are always unique within the field. */
export function optionsFromLines(text:string,previous:Option[]=[]):Option[]{
 const labels=text.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
 const pool=[...previous],values:(string|null)[]=labels.map(label=>{
  const at=pool.findIndex(option=>option.label.trim()===label);
  return at<0?null:pool.splice(at,1)[0].value;
 });
 const used=new Set<string>(),earlier=new Set(previous.map(option=>option.value));
 values.forEach((value,index)=>{if(value==null)return;if(used.has(value))values[index]=null;else used.add(value);});
 const taken=(value:string)=>used.has(value)||earlier.has(value);
 return labels.map((label,index)=>{
  let value=values[index];
  if(value==null){
   const base=slug(label);
   if(base){value=base;for(let n=2;taken(value);n++)value=`${base}_${n}`;}
   else{let n=1;while(taken(`opt_${n}`))n++;value=`opt_${n}`;}
   used.add(value);
  }
  return {value,label};
 });
}
export const optionLines=(options:Option[])=>options.map(option=>option.label).join('\n');

/** The schema as the server stores it: no builder state, options only on select questions, unit and
 * min/max only on numeric ones, qualitative only on text, empty constraints and sections removed. */
export function cleanSchema(schema:SchemaLike):FormSchema{
 const finite=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value:null;
 const fields=schema.fields.map((f):FormField=>{
  const numeric=isNumeric(f.type),min=numeric?finite(f.constraints?.min):null,max=numeric?finite(f.constraints?.max):null;
  const constraints:{min?:number;max?:number}={};
  if(min!=null)constraints.min=min;
  if(max!=null)constraints.max=max;
  return {
   id:f.id,type:f.type,label:f.label.trim(),required:!!f.required,
   options:isSelect(f.type)?(f.options||[]).map(o=>({value:o.value,label:o.label.trim()})):[],
   unit:numeric?f.unit?.trim()||null:null,
   constraints:min==null&&max==null?null:constraints,
   pii:!!f.pii,qualitative:f.type==='text'&&!!f.qualitative,section:f.section?.trim()||null,
  };
 });
 return {schema_version:1,title:schema.title.trim(),entity_key_field:schema.entity_key_field||null,fields,origin:schema.origin??null,source:schema.source??null};
}

/** A saved schema made editable. `uids` (in field order) keeps the React keys of questions just saved;
 * `reserved` adds ids new questions must not take (see BuilderSchema.reserved). */
export function toBuilder(schema:FormSchema,uids:string[]=[],reserved:Iterable<string>=[]):BuilderSchema{
 const keep=uids.length===schema.fields.length;
 const fields=schema.fields.map((f,index)=>({...f,options:f.options||[],uid:keep?uids[index]:nextUid(),optionsText:optionLines(f.options||[])}));
 const key=schema.entity_key_field;
 return {...schema,reserved:[...new Set([...schema.fields.map(f=>f.id),...reserved])],fields,entityUid:key?fields.find(f=>f.id===key)?.uid??null:null};
}
/** Ids already used by the other questions, plus the reserved ones. */
const takenIds=(schema:BuilderSchema,except?:string)=>[...schema.fields.filter(f=>f.uid!==except).map(f=>f.id),...(schema.reserved||[])];

/** The fields with the one at `index` moved by `delta` places (unchanged copy when it cannot move). */
export function moveField<T>(fields:T[],index:number,delta:number):T[]{
 const to=index+delta,out=[...fields];
 if(index<0||index>=fields.length||to<0||to>=fields.length)return out;
 const [field]=out.splice(index,1);
 out.splice(to,0,field);
 return out;
}

/** A new empty text question at the end (its id is free and follows its label until saved). */
export function addField(schema:BuilderSchema,uid=nextUid()):{schema:BuilderSchema;uid:string}{
 const id=newFieldId('',takenIds(schema));
 return {uid,schema:{...schema,fields:[...schema.fields,{uid,id,type:'text',label:'',required:false,options:[],optionsText:'',unit:null,constraints:null,pii:false,qualitative:false,section:null,fresh:true,autoId:true}]}};
}

/** Changing a question's type drops what the new type cannot have. */
export function changeType(field:BuilderField,type:FieldType):BuilderField{
 const next:BuilderField={...field,type};
 if(!isSelect(type)){next.options=[];next.optionsText='';}
 if(!isNumeric(type)){next.constraints=null;next.unit=null;}
 if(type!=='text')next.qualitative=false;
 return next;
}

function patchField(schema:BuilderSchema,uid:string,change:(f:BuilderField)=>BuilderField):BuilderSchema{
 return {...schema,fields:schema.fields.map(f=>f.uid===uid?change(f):f)};
}

/** The identifier question: the one recorded by uid while it still has the identifier's id, else the first
 * question with that id (entity_key_field set without the builder, e.g. a schema made by hand). Only this
 * question's rename, removal or type change moves or clears the identifier, never another question's that
 * happens to have the same id while its id is typed. */
export function entityOwner(schema:BuilderSchema):BuilderField|undefined{
 const key=schema.entity_key_field;
 if(!key)return undefined;
 return schema.fields.find(f=>f.uid===schema.entityUid&&f.id===key)??schema.fields.find(f=>f.id===key);
}
const noEntity={entity_key_field:null,entityUid:null};

/** The identifier chosen by id (the first question with that id), or none. */
export function setEntity(schema:BuilderSchema,id:string|null):BuilderSchema{
 return id?{...schema,entity_key_field:id,entityUid:schema.fields.find(f=>f.id===id)?.uid??null}:{...schema,...noEntity};
}

export function setFieldType(schema:BuilderSchema,uid:string,type:FieldType):BuilderSchema{
 const next=patchField(schema,uid,f=>changeType(f,type));
 return entityOwner(schema)?.uid===uid&&!isKeyType(type)?{...next,...noEntity}:next;
}

/** A new label; a new question whose id still follows its label gets a fresh id. */
export function setFieldLabel(schema:BuilderSchema,uid:string,label:string):BuilderSchema{
 const field=schema.fields.find(f=>f.uid===uid);
 if(!field)return schema;
 if(!field.fresh||!field.autoId)return patchField(schema,uid,f=>({...f,label}));
 const id=newFieldId(label,takenIds(schema,uid));
 return setFieldId(patchField(schema,uid,f=>({...f,label})),uid,id,true);
}

/** Only new questions can be renamed; the identifier follows the rename of its own question only. */
export function setFieldId(schema:BuilderSchema,uid:string,id:string,auto=false):BuilderSchema{
 const field=schema.fields.find(f=>f.uid===uid);
 if(!field?.fresh)return schema;
 const next=patchField(schema,uid,f=>({...f,id,autoId:auto&&f.autoId}));
 return entityOwner(schema)?.uid===uid?{...next,entity_key_field:id,entityUid:uid}:next;
}

/** The options text as typed; values of unchanged labels are kept (saved values first), and a new label
 * never takes a saved value (so a removed or renamed saved option shows as lost). */
export function setOptionsText(schema:BuilderSchema,uid:string,text:string,saved:Option[]=[]):BuilderSchema{
 return patchField(schema,uid,f=>({...f,optionsText:text,options:optionsFromLines(text,[...saved,...f.options])}));
}

/** Removing the identifier question clears the identifier (it never passes to a question with the same id). */
export function removeField(schema:BuilderSchema,uid:string):BuilderSchema{
 const next={...schema,fields:schema.fields.filter(f=>f.uid!==uid)};
 return entityOwner(schema)?.uid===uid?{...next,...noEntity}:next;
}

/** A min/max as typed in a number input: empty or not a finite number means no bound. */
export function parseBound(raw:string):number|null{
 if(!raw.trim())return null;
 const value=Number(raw);
 return Number.isFinite(value)?value:null;
}
/** The value of a min/max number input: the number itself, not its text. React rewrites a controlled number
 * input only when its text is not loosely equal to the value, so "0.0" (on the way to 0.05) or "-0" stays as
 * typed; with String(0) = "0" it would become "0", and the next key would make 5. */
export const boundValue=(value:number|null|undefined):number|''=>value??'';

/** The server's form rules (validate_form), in Arabic, each tied to the question index and the input. */
export function validateFormSchema(schema:SchemaLike):SchemaIssue[]{
 const issues:SchemaIssue[]=[],seen=new Set<string>();
 if(!schema.title.trim())issues.push({field:null,part:'title',message:'اكتب عنوان النموذج.'});
 if(!schema.fields.length)issues.push({field:null,part:'fields',message:'أضف سؤالاً واحداً على الأقل.'});
 schema.fields.forEach((f,index)=>{
  const add=(part:SchemaIssue['part'],message:string)=>issues.push({field:index,part,message});
  if(!FIELD_ID.test(f.id))add('id','المعرّف يبدأ بحرف لاتيني صغير، ويتكوّن من أحرف لاتينية صغيرة وأرقام وشرطة سفلية (_) فقط، بحد أقصى ٦٣ حرفاً.');
  if(seen.has(f.id))add('id','هذا المعرّف مستخدم لسؤال آخر في النموذج. اختر معرّفاً مختلفاً.');
  seen.add(f.id);
  if(!f.label.trim())add('label','اكتب نص السؤال.');
  const options=f.options||[];
  if(isSelect(f.type)){
   if(options.length<2)add('options','أضف خيارين على الأقل، كل خيار في سطر.');
   if(new Set(options.map(o=>o.value)).size!==options.length)add('options','يوجد خياران بالقيمة المخزنة نفسها. أعد كتابة الخيارات المكررة.');
  }else if(options.length)add('options','الخيارات مسموحة فقط في أسئلة الاختيار.');
  const c=f.constraints;
  if(c&&(c.min!=null||c.max!=null)){
   if(!isNumeric(f.type))add('constraints','الحدان الأدنى والأعلى مسموحان فقط في الأسئلة الرقمية.');
   else if(c.min!=null&&c.max!=null&&c.min>c.max)add('constraints','الحد الأدنى أكبر من الحد الأعلى، فلن تُقبل أي إجابة.');
  }
 });
 if(schema.entity_key_field!=null){
  const key=schema.fields.find(f=>f.id===schema.entity_key_field);
  if(!key)issues.push({field:null,part:'entity',message:'سؤال المعرّف المختار لم يعد موجوداً في النموذج. اختر سؤالاً آخر أو «دون معرّف».'});
  else if(!isKeyType(key.type))issues.push({field:null,part:'entity',message:'سؤال المعرّف يجب أن يكون من نوع نص أو عدد صحيح.'});
 }
 return issues;
}

/** Consecutive questions under the same section heading (empty section: no heading). */
export function groupBySection<T extends {section?:string|null}>(fields:T[]):{section:string|null;fields:T[]}[]{
 const groups:{section:string|null;fields:T[]}[]=[];
 for(const field of fields){
  const section=field.section?.trim()||null,last=groups[groups.length-1];
  if(last&&last.section===section)last.fields.push(field);
  else groups.push({section,fields:[field]});
 }
 return groups;
}

/** What the calculation rules read from one form: the indicators, the field ids, and whether a rule
 * counts distinct people/things (which needs the identifier question). */
export function rulesReading(definitions:{indicator_id:string;definition:unknown}[],formKey:string):{indicators:string[];fields:Set<string>;entity:boolean}{
 const indicators:string[]=[],fields=new Set<string>();
 let entity=false;
 for(const d of definitions){
  if(!formsInDefinition(d.definition).includes(formKey))continue;
  if(!indicators.includes(d.indicator_id))indicators.push(d.indicator_id);
  (function walk(value:unknown,inForm:boolean){
   if(Array.isArray(value)){value.forEach(item=>walk(item,inForm));return;}
   if(!value||typeof value!=='object')return;
   const o=value as Record<string,unknown>,here=typeof o.form==='string'?o.form===formKey:inForm;
   if(here&&typeof o.field==='string')fields.add(o.field);
   if(o.form===formKey&&o.unit==='entity')entity=true;
   for(const [key,inner] of Object.entries(o)){
    if(key==='disaggregate_by'&&Array.isArray(inner))inner.forEach(id=>{if(typeof id==='string')fields.add(id);});
    else walk(inner,here);
   }
  })(d.definition,false);
 }
 return {indicators,fields,entity};
}

/** First-strong isolate: a Latin id inside an Arabic sentence keeps its own direction. */
const FSI=String.fromCharCode(0x2068),PDI=String.fromCharCode(0x2069);
const isolate=(text:string)=>FSI+text+PDI;
const serverMessages:[RegExp,(m:RegExpMatchArray)=>string][]=[
 [/^title is empty$/,()=>'عنوان النموذج فارغ.'],
 [/^form has no fields$/,()=>'النموذج لا يحتوي على أي سؤال.'],
 [/^field '(.*)': id must match/,m=>`السؤال ${isolate(m[1])}: المعرّف غير صالح.`],
 [/^field '(.*)': duplicate id$/,m=>`السؤال ${isolate(m[1])}: المعرّف مكرر.`],
 [/^field '(.*)': label is empty$/,m=>`السؤال ${isolate(m[1])}: نص السؤال فارغ.`],
 [/^field '(.*)': select_(?:one|multiple) needs at least two options$/,m=>`السؤال ${isolate(m[1])}: يحتاج إلى خيارين على الأقل.`],
 [/^field '(.*)': option values must be unique$/,m=>`السؤال ${isolate(m[1])}: قيم الخيارات مكررة.`],
 [/^field '(.*)': options are only allowed on select fields$/,m=>`السؤال ${isolate(m[1])}: الخيارات مسموحة فقط في أسئلة الاختيار.`],
 [/^field '(.*)': min\/max constraints are only allowed on numeric fields$/,m=>`السؤال ${isolate(m[1])}: الحدان الأدنى والأعلى مسموحان فقط في الأسئلة الرقمية.`],
 [/^entity_key_field '(.*)' is not a field of the form$/,m=>`سؤال المعرّف ${isolate(m[1])} غير موجود في النموذج.`],
 [/^entity_key_field must be a text or integer field$/,()=>'سؤال المعرّف يجب أن يكون من نوع نص أو عدد صحيح.'],
];
/** The server's form validation messages in Arabic; anything else is returned as it is. */
export function arabicDetail(text:string):string{
 for(const [pattern,message] of serverMessages){const match=text.match(pattern);if(match)return message(match);}
 return text;
}
