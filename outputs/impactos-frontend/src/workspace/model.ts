import type {Draft,Dashboard,FormSchema,FormField,FieldError} from './types';
export function emptyDraft():Draft { return {results:[],indicators:[],forms:[],definitions:[],open_questions:[]}; }
export function emptyDashboard():Dashboard { return {published:false,results:[],summary:{total:0,achieved:0,in_progress:0,not_started:0,no_target:0,not_computable:0},indicators:[],submissions:{}}; }
export function validateFiles(files:Pick<File,'name'|'size'>[]):string[] {
 const errors:string[]=[];
 if(!files.length)errors.push('اختر ملفاً واحداً على الأقل.');
 for(const file of files){
  if(!/\.(xlsx|xlsm|csv|docx|pdf)$/i.test(file.name))errors.push(`${file.name}: اختر ملف Excel أو CSV أو Word أو PDF نصي.`);
  if(file.size>25*1024*1024)errors.push(`${file.name}: حجم الملف يتجاوز الحد المسموح، ٢٥ ميغابايت.`);
  if(file.size===0)errors.push(`${file.name}: الملف فارغ. اختر ملفاً يحتوي على بيانات.`);
 }
 return errors;
}
export function validateFormAnswers(schema:FormSchema,answers:Record<string,unknown>):FieldError[]{
 const errors:FieldError[]=[];
 for(const f of schema.fields){
  const value=answers[f.id],error=(message:string)=>errors.push({field:f.id,message});
  if(value==null||value===''||(Array.isArray(value)&&value.length===0)){if(f.required)error('هذا الحقل مطلوب.');continue;}
  if(f.type==='integer'||f.type==='decimal'){
   if(typeof value!=='number'||!Number.isFinite(value)||(f.type==='integer'&&!Number.isInteger(value)))error(f.type==='integer'?'أدخل عدداً صحيحاً.':'أدخل قيمة رقمية صحيحة.');
   else if((f.constraints?.min!=null&&value<f.constraints.min)||(f.constraints?.max!=null&&value>f.constraints.max))error(`القيمة المطلوبة بين ${f.constraints?.min??'−∞'} و${f.constraints?.max??'∞'}.`);
  }
  if(f.type==='text'&&typeof value!=='string')error('أدخل إجابة نصية.');
  if(f.type==='select_one'&&!f.options.some(o=>o.value===value))error('اختر إجابة من الخيارات المتاحة.');
  if(f.type==='select_multiple'&&(!Array.isArray(value)||new Set(value).size!==value.length||value.some(v=>!f.options.some(o=>o.value===v))))error('اختر إجابات صالحة دون تكرار.');
  if(f.type==='date'&&(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||Number.isNaN(Date.parse(value))||new Date(value).toISOString().slice(0,10)!==value))error('أدخل تاريخاً صحيحاً.');
 }
 return errors;
}
export function metric(value:number|null|undefined,unit?:string|null):string{return value==null?'—':`${new Intl.NumberFormat('ar-JO',{maximumFractionDigits:2}).format(value)}${unit==='%'?'٪':''}`;}
export function dateLabel(value:string):string {const date=new Date(value);return Number.isNaN(date.valueOf())?value:new Intl.DateTimeFormat('ar-JO',{dateStyle:'medium',timeStyle:'short'}).format(date);}
export const statusLabels:Record<string,string>={draft:'مسودة',published:'منشور',approved:'معتمد',uploaded:'تم الرفع',parsing:'جارٍ قراءة الملفات',parsed:'تمت قراءة الملفات',extracting:'جارٍ استخراج الإطار',extracted:'جاهز للمراجعة',failed:'تعذرت المعالجة',ok:'قيمة محسوبة',no_data:'لا توجد بيانات',not_computable:'غير قابل للحساب',manual:'إدخال يدوي',not_due:'لم يحن موعده',achieved:'تحقق المستهدف',in_progress:'قيد التقدم',not_started:'لم يبدأ بعد',no_target:'دون مستهدف'};
export const kindLabels:Record<string,string>={count:'عدد',sum:'مجموع',average:'متوسط',ratio:'نسبة',milestone:'إنجاز مرحلي'};
export const trackLabels:Record<string,string>={achieved:'تحقق المستهدف',in_progress:'قيد التقدم',not_started:'لم يبدأ بعد',no_target:'دون مستهدف',not_computable:'غير قابل للحساب'};
export const originLabels:Record<string,string>={document:'من ملفاتك',ai:'مقترح آلياً',manual:'أُنشئ يدوياً'};
export const fieldTypeLabels:Record<string,string>={text:'نص',integer:'عدد صحيح',decimal:'رقم عشري',select_one:'اختيار واحد',select_multiple:'اختيارات متعددة',date:'تاريخ'};
/** One readable line per server error detail: plain strings, request-validation items ({loc,msg}) and publish problems ({form|indicator_id, errors}). */
export function detailText(item:unknown,names:Record<string,string>={}):string{
 if(typeof item==='string')return item;
 if(item&&typeof item==='object'){
  const o=item as Record<string,unknown>;
  if(typeof o.msg==='string')return [Array.isArray(o.loc)?o.loc.filter(part=>part!=='body').join('.'):'',o.msg].filter(Boolean).join(': ');
  if(Array.isArray(o.errors)){const who=typeof o.form==='string'?`النموذج ${names[o.form]||o.form}`:typeof o.indicator_id==='string'?`المؤشر ${names[o.indicator_id]||o.indicator_id}`:'';return [who,o.errors.map(String).join('؛ ')].filter(Boolean).join(': ');}
 }
 return JSON.stringify(item);
}
/** Keys of every form a calculation rule reads. */
export function formsInDefinition(definition:unknown):string[]{const out=new Set<string>();(function walk(value:unknown){if(Array.isArray(value))value.forEach(walk);else if(value&&typeof value==='object')for(const [key,inner] of Object.entries(value)){if(key==='form'&&typeof inner==='string')out.add(inner);else walk(inner);}})(definition);return [...out];}
/** A parameter of the current hash route, e.g. hashParam('form') on #/forms?form=survey. Screens are remounted when the route changes, so reading it on mount is enough. */
export function hashParam(name:string,hash:string=window.location.hash):string|null{return new URLSearchParams(hash.split('?')[1]||'').get(name);}
/** Consecutive fields that share a `section` form one group; fields without a section form groups without a heading. */
export function sectionGroups(fields:FormField[]):{section:string|null;fields:FormField[]}[]{
 const groups:{section:string|null;fields:FormField[]}[]=[];
 for(const field of fields){
  const section=field.section?.trim()||null,last=groups[groups.length-1];
  if(last&&last.section===section)last.fields.push(field);else groups.push({section,fields:[field]});
 }
 return groups;
}
