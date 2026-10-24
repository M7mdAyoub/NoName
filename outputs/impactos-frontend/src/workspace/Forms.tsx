// Form builder (#/forms): the forms of the draft (found in the uploaded files, proposed by the AI or made
// here), an editor for draft forms, and a live preview of what a data collector sees.
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Plus,Trash2,ArrowUp,ArrowDown,Save,RotateCcw,Eye,LayoutTemplate,ShieldCheck,Lock,ArrowLeft,PlugZap,Copy,ListPlus} from 'lucide-react';
import {useWorkspace} from './Context';
import {Heading,EmptyState,Status,Dialog,OriginBadge,SearchBox,count} from './UI';
import {fieldTypeLabels,hashParam,detailText} from './model';
import {cleanSchema,toBuilder,addField,nextUid,moveField,removeField,setFieldType,setFieldLabel,setFieldId,setEntity,entityOwner,setOptionsText,parseBound,boundValue,validateFormSchema,groupBySection,rulesReading,arabicDetail,isSelect,isNumeric,isKeyType,optionLines,type BuilderField,type BuilderSchema,type SchemaIssue} from './builder';
import type {ApiError} from './api';
import type {FieldType,FormRow,FormSchema} from './types';

/** The form being edited: its saved version (raw as the server sent it, and cleaned for comparing) and
 * the edits. `stale` is the server version from before our own save, ignored until the draft is reloaded. */
type Editing={key:string;saved:FormSchema;raw:string;savedJson:string;schema:BuilderSchema;stale?:string};
type Pending={kind:'select';key:string}|{kind:'create'}|{kind:'discard'};
type Action='create'|'copy'|'save'|'delete';

/** `reserved`: ids new questions must not take (the ones calculation rules read, see BuilderSchema.reserved). */
function start(row:FormRow,uids?:string[],reserved:Iterable<string>=[]):Editing{return {key:row.key,saved:row.schema,raw:JSON.stringify(row.schema),savedJson:JSON.stringify(cleanSchema(row.schema)),schema:toBuilder(row.schema,uids,reserved)};}
/** Numbers of a question's allowed range, without the rounding of metric() (a minimum of 0.005 stays 0.005). */
const exact=(value:number|null|undefined)=>value==null?'—':new Intl.NumberFormat('ar-JO',{maximumFractionDigits:6}).format(value);
const isDirty=(editing:Editing|null)=>!!editing&&JSON.stringify(cleanSchema(editing.schema))!==editing.savedJson;
const leaveMessage='لديك تعديلات غير محفوظة على النموذج. هل تريد المغادرة دون حفظها؟';
/** The first question of a new form; the server needs at least one. */
const starterSchema:Omit<FormSchema,'title'>={schema_version:1,fields:[{id:'q_1',type:'text',label:'سؤال جديد',required:false,options:[]}],origin:'manual'};

export default function Forms(){
 const {draft,connected,busy,error,run,refresh,setUnsaved}=useWorkspace();
 const [selected,setSelected]=useState<string|null>(()=>hashParam('form'));
 const [editing,setEditing]=useState<Editing|null>(null);
 const [pending,setPending]=useState<Pending|null>(null);
 const [confirmDelete,setConfirmDelete]=useState(false);
 const [failed,setFailed]=useState<Action|null>(null);
 const [working,setWorking]=useState<Action|null>(null);
 const [focus,setFocus]=useState<string|null>(null);
 const [query,setQuery]=useState('');
 // The router (Workspace) keeps this screen while the address keeps the hash it was opened with; `address`
 // is the hash as this screen last saw it (select() rewrites it without an event).
 const [entered]=useState(()=>window.location.hash);
 const address=useRef(entered);

 const current=draft.forms.find(f=>f.key===selected)||draft.forms[0]||null;
 const currentJson=current?JSON.stringify(current.schema):'';
 const reading=rulesReading(current?draft.definitions:[],current?.key??'');
 // Follow the selected form and its saved version while rendering (no frame with a stale editor).
 // Unsaved edits survive a reload that brings a newer version of the same form.
 if(!current){if(editing)setEditing(null);}
 else if(!editing||editing.key!==current.key)setEditing(start(current,undefined,reading.fields));
 else if(currentJson!==editing.raw&&currentJson!==editing.stale)setEditing(isDirty(editing)?{...editing,saved:current.schema,raw:currentJson,savedJson:JSON.stringify(cleanSchema(current.schema)),stale:undefined,schema:{...editing.schema,reserved:[...new Set([...(editing.schema.reserved||[]),...current.schema.fields.map(f=>f.id),...reading.fields])]}}:start(current,undefined,[...(editing.schema.reserved||[]),...reading.fields]));
 // Published meanwhile (another tab, then a reload): show what the server has, not edits that can no longer be saved.
 else if(current.status==='published'&&isDirty(editing))setEditing(start(current,undefined,reading.fields));

 const live=editing&&current&&editing.key===current.key?editing:null;
 const readOnly=current?.status==='published';
 const dirty=!readOnly&&isDirty(live);
 const issues=live&&!readOnly?validateFormSchema(cleanSchema(live.schema)):[];

 useEffect(()=>{const seen=()=>{address.current=window.location.hash;};window.addEventListener('hashchange',seen);return()=>window.removeEventListener('hashchange',seen);},[]);
 // Unsaved changes: ask before closing the tab or leaving this screen. The router's hashchange listener was
 // added first and its update renders at once, unmounting this screen before a hashchange listener here
 // runs, so leaving is caught earlier: in-app links on click (capture, before the hash changes) and
 // Back/Forward on popstate (fired before hashchange). Reconnecting asks through setUnsaved.
 useEffect(()=>{
  setUnsaved(dirty?leaveMessage:null);
  if(!dirty)return;
  /** The hash a confirmed link click goes to (its popstate does not ask again); what a cancelled Back/Forward restores. */
  let allowed:string|null=null,restore:{hash:string;top:number}|null=null;
  const beforeUnload=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=leaveMessage;};
  const click=(e:MouseEvent)=>{
   const link=e.target instanceof Element?e.target.closest<HTMLAnchorElement>('a[href^="#/"]'):null;
   if(!link||e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||(link.target&&link.target!=='_self'))return;
   const hash=new URL(link.href).hash;
   // Same address, or the hash this screen was opened with: the router keeps this screen and the edits.
   if(hash===window.location.hash||hash===entered)return;
   if(window.confirm(leaveMessage))allowed=hash;else e.preventDefault();
  };
  const popState=()=>{
   const hash=window.location.hash,confirmed=hash===allowed;
   allowed=null;
   if(confirmed||hash===address.current||hash===entered||window.confirm(leaveMessage))return;
   // Stay. The router reads the address in the hashchange that follows: give it the hash it already has,
   // as a new entry (the entry moved to stays in the history), then show the exact address again below.
   restore={hash:address.current,top:window.scrollY};
   try{history.pushState(history.state,'',entered);}catch{restore=null;}
  };
  const hashChange=()=>{
   if(!restore)return;
   const {hash,top}=restore;
   restore=null;
   try{history.replaceState(history.state,'',hash);address.current=hash;}catch{}
   window.scrollTo({top});
  };
  window.addEventListener('beforeunload',beforeUnload);
  document.addEventListener('click',click,true);
  window.addEventListener('popstate',popState);
  window.addEventListener('hashchange',hashChange);
  return()=>{setUnsaved(null);window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('click',click,true);window.removeEventListener('popstate',popState);window.removeEventListener('hashchange',hashChange);};
 },[dirty,entered]);

 useEffect(()=>{if(!focus)return;const element=document.getElementById(focus);element?.focus();setFocus(null);},[focus,live]);

 const indicatorNames=Object.fromEntries(draft.indicators.map(i=>[i.id,i.name]));
 const feeds=(key:string)=>rulesReading(draft.definitions,key).indicators.filter(id=>id in indicatorNames);
 const update=(change:(schema:BuilderSchema)=>BuilderSchema)=>setEditing(old=>old&&{...old,schema:change(old.schema)});

 function select(key:string|null){
  setSelected(key);setFailed(null);setConfirmDelete(false);
  try{history.replaceState(history.state,'',key?`#/forms?form=${encodeURIComponent(key)}`:'#/forms');address.current=window.location.hash;}catch{}
 }
 function choose(key:string){if(key===current?.key)return;if(dirty)setPending({kind:'select',key});else select(key);}
 function discard(){setEditing(old=>old&&{...old,schema:toBuilder(old.saved,[],old.schema.reserved)});}
 async function act<T>(action:Action,work:()=>Promise<T|null>):Promise<T|null>{
  setFailed(null);setWorking(action);
  try{const result=await work();if(result===null)setFailed(action);return result;}finally{setWorking(null);}
 }
 async function create(){
  const row=await act('create',()=>run(api=>api.createForm('نموذج جديد',starterSchema),'تم إنشاء نموذج جديد. غيّر عنوانه وأسئلته ثم احفظه.',{inline:true}));
  // The button that started this may be gone (the empty state, or the dialog): continue on the new form's title.
  if(row){await refresh();select(row.key);setFocus('builder-title');}
 }
 async function copy(row:FormRow){
  const clean=cleanSchema(row.schema);
  const created=await act('copy',()=>run(api=>api.createForm(`نسخة من ${row.title}`,{schema_version:1,entity_key_field:clean.entity_key_field,fields:clean.fields,origin:'manual',source:null}),'تم إنشاء نسخة قابلة للتعديل من النموذج.',{inline:true}));
  // The copy button belongs to the read-only form: continue on the copy's title.
  if(created){await refresh();select(created.key);setFocus('builder-title');}
 }
 async function save():Promise<boolean>{
  if(!live||readOnly||issues.length)return false;
  const key=live.key,schema=cleanSchema(live.schema),sent=JSON.stringify(schema),uids=live.schema.fields.map(f=>f.uid),before=currentJson;
  const row=await act('save',()=>run(api=>api.saveForm(key,schema),'تم حفظ النموذج.',{inline:true}));
  if(!row)return false;
  const next={...start(row,uids,[...(live.schema.reserved||[]),...reading.fields]),stale:before};
  setEditing(old=>{
   if(!old||old.key!==key)return old;
   if(JSON.stringify(cleanSchema(old.schema))===sent)return next;
   // Edits typed while the save was on its way stay (still unsaved); the questions just saved are no longer new.
   const ids=new Set(row.schema.fields.map(f=>f.id));
   return {...next,schema:{...old.schema,reserved:next.schema.reserved,fields:old.schema.fields.map(f=>f.fresh&&ids.has(f.id)?{...f,fresh:false,autoId:false}:f)}};
  });
  await refresh();
  return true;
 }
 async function remove(){
  if(!current)return;
  const key=current.key;
  const done=await act('delete',()=>run(api=>api.deleteForm(key),'تم حذف النموذج من المسودة.',{inline:true}));
  if(!done)return;
  setConfirmDelete(false);
  await refresh();
  select(null);
 }
 async function proceed(action:Pending,saveFirst:boolean){
  setPending(null);
  if(saveFirst){if(!await save())return;}else discard();
  if(action.kind==='select')select(action.key);
  else if(action.kind==='create')await create();
 }
 function focusIssue(issue:SchemaIssue){
  if(!live)return;
  if(issue.field==null){setFocus(issue.part==='title'?'builder-title':issue.part==='entity'?'builder-entity':'builder-add');return;}
  const field=live.schema.fields[issue.field],base=`builder-${field.uid}`;
  const target=issue.part==='label'?`${base}-label`:issue.part==='options'?`${base}-options`:issue.part==='constraints'?`${base}-min`:issue.part==='id'&&field.fresh?`${base}-id`:base;
  setFocus(document.getElementById(target)?target:base);
 }

 const createButton=(primary:boolean)=><button className={primary?'q-btn q-primary':'q-btn'} disabled={!connected||busy} onClick={()=>dirty?setPending({kind:'create'}):create()}><Plus size={18}/>{working==='create'?'جارٍ الإنشاء…':'نموذج جديد'}</button>;
 // The search box shows only for a long list; the query filters only while it is shown (after a deletion
 // the box can disappear, and a hidden query would hide forms with no way to clear it).
 const searching=draft.forms.length>6;
 const listed=searching?draft.forms.filter(f=>f.title.toLowerCase().includes(query.trim().toLowerCase())):draft.forms;

 return <><Heading title="منشئ النماذج" description="راجع النماذج المستخرجة من ملفاتك، وعدّل أسئلتها، وشاهد كيف تظهر لجامع البيانات قبل النشر." action={connected&&draft.forms.length>0?createButton(false):undefined}/>
 {failed==='create'&&error&&<ServerProblem error={error} action="create"/>}
 {!connected?<section className="q-panel"><EmptyState title={busy?'جارٍ الاتصال بالخادم…':'الخادم غير متصل'} description={busy?'نحمّل نماذج المشروع من الخادم.':'اربط خادم المشروع من زر «ربط الخادم» أعلى الصفحة لعرض النماذج وتعديلها. لا تعرض الواجهة نماذج افتراضية.'} icon={<PlugZap size={28}/>}/></section>
 :!current||!live?<section className="q-panel"><EmptyState title="لا توجد نماذج بعد" description="ارفع إطار النتائج ليستخرج النظام النماذج الموجودة في ملفاتك، أو أنشئ نموذجاً جديداً وأضف أسئلته بنفسك." icon={<LayoutTemplate size={28}/>}><div className="q-builder-empty-actions"><a className="q-btn" href="#/framework">رفع إطار النتائج<ArrowLeft size={17}/></a>{createButton(true)}</div></EmptyState></section>
 :<div className="q-builder">
  <section className="q-panel q-builder-list" aria-labelledby="builder-list-title">
   <div className="q-builder-list-head"><h2 id="builder-list-title">النماذج</h2><span className="q-tab-count">{count(draft.forms.length)}</span></div>
   {searching&&<div className="q-builder-search"><SearchBox value={query} onChange={setQuery} label="ابحث عن نموذج"/></div>}
   <ul>{listed.map(row=>{const active=row.key===current.key,feeding=feeds(row.key).length;return <li key={row.key}><button className="q-builder-item" aria-current={active?'true':undefined} onClick={()=>choose(row.key)}>
    <strong dir="auto">{row.title}</strong>
    <span className="q-builder-item-tags"><OriginBadge origin={row.schema.origin} source={row.schema.source}/><Status value={row.status}/></span>
    <small>{count(row.schema.fields.length)} أسئلة · {feeding?`يغذي ${count(feeding)} مؤشرات`:'لا يغذي مؤشرات بعد'}</small>
   </button></li>;})}</ul>
   {!listed.length&&<p className="q-inline-empty">لا توجد نماذج تطابق البحث.</p>}
  </section>
  <Editor key={current.key} row={current} editing={live} readOnly={readOnly} dirty={dirty} issues={issues} indicatorNames={indicatorNames} reading={reading} busy={busy} working={working} failed={failed} error={error} update={update} focus={setFocus} focusIssue={focusIssue} onSave={()=>void save()} onDiscard={()=>setPending({kind:'discard'})} onDelete={()=>{setFailed(null);setConfirmDelete(true);}} onCopy={()=>void copy(current)}/>
  <Preview key={`preview-${current.key}`} schema={live.schema}/>
 </div>}
 {pending&&live&&<Dialog title={pending.kind==='discard'?'تجاهل التعديلات؟':'تعديلات غير محفوظة'} onClose={()=>setPending(null)}>
  <p className="q-dialog-intro">{pending.kind==='discard'?'ستعود الأسئلة إلى آخر نسخة محفوظة في الخادم، وتُفقد التعديلات الحالية.':<>لم تحفظ تعديلاتك على «<bdi>{live.schema.title.trim()||current?.title}</bdi>». إذا تابعت دون حفظ ستُفقد هذه التعديلات.</>}</p>
  {pending.kind!=='discard'&&issues.length>0&&<div className="q-callout">لا يمكن الحفظ الآن: في النموذج {count(issues.length)} ملاحظات تحتاج إلى تصحيح.</div>}
  <div className="q-dialog-actions"><button className="q-btn" onClick={()=>setPending(null)}>متابعة التعديل</button><button className={pending.kind==='discard'?'q-btn q-primary':'q-btn'} onClick={()=>void proceed(pending,false)}><RotateCcw size={17}/>تجاهل التعديلات</button>{pending.kind!=='discard'&&<button className="q-btn q-primary" disabled={busy||issues.length>0} onClick={()=>void proceed(pending,true)}><Save size={17}/>حفظ ثم المتابعة</button>}</div>
 </Dialog>}
 {confirmDelete&&current&&<Dialog title="حذف النموذج" onClose={()=>{if(working!=='delete')setConfirmDelete(false);}}>
  <p className="q-dialog-intro">سيُحذف النموذج «<bdi>{current.title}</bdi>» وأسئلته من المسودة. لا يمكن حذف نموذج منشور، ولا نموذج تقرأ قاعدة حساب إجاباته.</p>
  {feeds(current.key).length>0&&<div className="q-callout">تقرأ قواعد حساب {count(feeds(current.key).length)} مؤشرات هذا النموذج: <span dir="auto">{feeds(current.key).map(id=>indicatorNames[id]).join('، ')}</span>. لذلك سيرفض الخادم حذفه. عدّل هذه القواعد أولاً من <a className="q-inline-link" href="#/review?tab=definitions">صفحة المراجعة</a>.</div>}
  {failed==='delete'&&error&&<ServerProblem error={error} action="delete"/>}
  <div className="q-dialog-actions"><button className="q-btn" disabled={working==='delete'} onClick={()=>setConfirmDelete(false)}>إلغاء</button><button className="q-btn q-primary q-builder-confirm-delete" disabled={busy} onClick={()=>void remove()}><Trash2 size={17}/>{working==='delete'?'جارٍ الحذف…':'حذف النموذج'}</button></div>
 </Dialog>}
 </>;
}

type EditorProps={row:FormRow;editing:Editing;readOnly:boolean;dirty:boolean;issues:SchemaIssue[];indicatorNames:Record<string,string>;reading:ReturnType<typeof rulesReading>;busy:boolean;working:Action|null;failed:Action|null;error:ApiError|null;update:(change:(schema:BuilderSchema)=>BuilderSchema)=>void;focus:(id:string)=>void;focusIssue:(issue:SchemaIssue)=>void;onSave:()=>void;onDiscard:()=>void;onDelete:()=>void;onCopy:()=>void};

function Editor({row,editing,readOnly,dirty,issues,indicatorNames,reading,busy,working,failed,error,update,focus,focusIssue,onSave,onDiscard,onDelete,onCopy}:EditorProps){
 const schema=editing.schema,fields=schema.fields;
 const fed=reading.indicators.filter(id=>id in indicatorNames);
 const sections=[...new Set(fields.map(f=>f.section?.trim()).filter((s):s is string=>!!s))];
 const keyFields=fields.filter(f=>isKeyType(f.type));
 const general=(part:SchemaIssue['part'])=>issues.filter(issue=>issue.field==null&&issue.part===part);
 const savedById=new Map(editing.saved.fields.map(f=>[f.id,f]));
 // What the calculation rules of this form would lose with the current edits (saving is still allowed).
 const warnings:ReactNode[]=[];
 for(const id of reading.fields){
  const before=savedById.get(id),now=fields.find(f=>f.id===id);
  if(!before)continue;
  if(!now)warnings.push(<>حذفت السؤال «<bdi>{before.label}</bdi>» الذي تقرؤه قاعدة حساب. ستحتاج القاعدة إلى تصحيح في صفحة المراجعة بعد الحفظ.</>);
  else if(now.fresh)warnings.push(<>السؤال الجديد «<bdi>{now.label||now.id}</bdi>» يحمل معرّف السؤال المحذوف «<bdi>{before.label}</bdi>» الذي تقرؤه قاعدة حساب، فستقرأ القاعدة إجابات السؤال الجديد بدلاً منه.</>);
  else if(now.type!==before.type)warnings.push(<>غيّرت نوع السؤال «<bdi>{now.label||before.label}</bdi>» الذي تقرؤه قاعدة حساب. تحقّق من القاعدة في صفحة المراجعة بعد الحفظ.</>);
  else if(isSelect(now.type)){
   // A rule compares answers with the stored option values: a renamed option gets a new value.
   const lost=(before.options||[]).filter(o=>!now.options.some(option=>option.value===o.value));
   if(lost.length)warnings.push(<>غيّرت خيارات السؤال «<bdi>{now.label||before.label}</bdi>» الذي تقرؤه قاعدة حساب، فلم تعد هذه الخيارات بقيمها المحفوظة: <bdi>{lost.map(o=>o.label).join('، ')}</bdi>. تحقّق من القاعدة في صفحة المراجعة بعد الحفظ.</>);
  }
 }
 if(reading.entity&&!schema.entity_key_field)warnings.push(<>قاعدة حساب تعدّ الأشخاص أو الأشياء المختلفة في هذا النموذج، وتحتاج إلى سؤال المعرّف.</>);
 const entityName=fields.find(f=>f.id===schema.entity_key_field)?.label;

 return <section className="q-panel q-builder-editor" aria-labelledby="builder-editor-title">
  <div className="q-builder-head">
   <h2 id="builder-editor-title" dir="auto">{schema.title.trim()||row.title}</h2>
   <div className="q-builder-meta"><OriginBadge origin={schema.origin} source={schema.source}/><Status value={row.status}/><span>مفتاح النموذج: <bdi>{row.key}</bdi></span></div>
   {schema.source&&<p className="q-field-hint">المصدر: <bdi dir="auto">{schema.source}</bdi></p>}
   <div className="q-builder-feeds">{fed.length?<><span>يغذي {count(fed.length)} مؤشرات:</span>{fed.map(id=><span className="q-tag" dir="auto" key={id}>{indicatorNames[id]}</span>)}</>:<span>لا تقرأ أي قاعدة حساب هذا النموذج بعد.</span>}</div>
  </div>
  {readOnly?<div className="q-builder-body">
   <div className="q-callout q-builder-locked"><Lock size={19}/><div><strong>هذا النموذج منشور ويجمع البيانات، لذلك لا يمكن تغيير أسئلته.</strong><p>لإضافة أسئلة أو تغييرها أنشئ نموذجاً جديداً، أو ابدأ من نسخة قابلة للتعديل من هذا النموذج.</p><button className="q-btn q-compact" disabled={busy} onClick={onCopy}><Copy size={16}/>{working==='copy'?'جارٍ النسخ…':'نسخ إلى نموذج جديد'}</button></div></div>
   {failed==='copy'&&error&&<ServerProblem error={error} action="copy"/>}
   {schema.entity_key_field&&<p className="q-field-hint">سؤال المعرّف: <bdi dir="auto">{entityName||schema.entity_key_field}</bdi></p>}
   <ol className="q-builder-readonly">{fields.map((f,index)=><li key={f.uid}>
    <div className="q-builder-card-top"><h3>السؤال {count(index+1)}</h3><span className="q-tag">{fieldTypeLabels[f.type]||f.type}</span>{f.required&&<span className="q-tag">مطلوب</span>}{f.pii&&<span className="q-tag">بيانات شخصية</span>}{f.qualitative&&<span className="q-tag">تحليل نوعي</span>}</div>
    <p className="q-builder-ro-label" dir="auto">{f.label}</p>
    <dl className="q-builder-ro-meta">
     <div><dt>المعرّف</dt><dd><bdi>{f.id}</bdi></dd></div>
     {f.section&&<div><dt>القسم</dt><dd dir="auto">{f.section}</dd></div>}
     {f.options.length>0&&<div><dt>الخيارات</dt><dd dir="auto">{f.options.map(o=>o.label).join(' / ')}</dd></div>}
     {f.unit&&<div><dt>الوحدة</dt><dd dir="auto">{f.unit}</dd></div>}
     {f.constraints&&(f.constraints.min!=null||f.constraints.max!=null)&&<div><dt>الحدود</dt><dd>من {exact(f.constraints.min)} إلى {exact(f.constraints.max)}</dd></div>}
    </dl>
   </li>)}</ol>
  </div>:<div className="q-builder-body">
   <label className="q-field-label">عنوان النموذج<input id="builder-title" dir="auto" value={schema.title} autoComplete="off" aria-invalid={general('title').length>0} aria-describedby={general('title').length?'builder-title-error':undefined} onChange={e=>update(s=>({...s,title:e.target.value}))}/></label>
   <Issues id="builder-title-error" list={general('title')}/>
   <label className="q-field-label">سؤال المعرّف<select id="builder-entity" value={schema.entity_key_field??''} aria-invalid={general('entity').length>0} aria-describedby={general('entity').length?'builder-entity-hint builder-entity-error':'builder-entity-hint'} onChange={e=>{const id=e.target.value||null;update(s=>setEntity(s,id));}}>
    <option value="">دون معرّف: يُحسب كل سجل</option>
    {keyFields.map(f=><option key={f.uid} value={f.id}>{(f.label.trim()||'سؤال دون نص')+' · '+f.id}</option>)}
    {schema.entity_key_field&&!keyFields.some(f=>f.id===schema.entity_key_field)&&<option value={schema.entity_key_field}>{schema.entity_key_field} (غير صالح)</option>}
   </select></label>
   <p className="q-field-hint" id="builder-entity-hint">يُستخدم لعدّ الأشخاص أو الأشياء المختلفة مرة واحدة، مثل رقم المستفيد أو رمز الأسرة، حتى لو تكررت سجلاتهم. اختر سؤالاً من نوع نص أو عدد صحيح.</p>
   <Issues id="builder-entity-error" list={general('entity')}/>
   <div className="q-builder-section-title"><h3>الأسئلة <span className="q-tab-count">{count(fields.length)}</span></h3></div>
   <p className="q-field-hint">معرّفات الأسئلة المحفوظة ثابتة، لأن قواعد الحساب والإجابات تشير إليها. يمكن تعديل معرّف السؤال الجديد فقط قبل حفظه.</p>
   <datalist id="builder-sections">{sections.map(s=><option key={s} value={s}/>)}</datalist>
   {fields.map((field,index)=><QuestionCard key={field.uid} field={field} index={index} total={fields.length} issues={issues.filter(issue=>issue.field===index)} used={!field.fresh&&reading.fields.has(field.id)} savedOptions={field.fresh?[]:savedById.get(field.id)?.options||[]} neighbour={(fields[index+1]||fields[index-1])?.uid??null} update={update} focus={focus}/>)}
   <button id="builder-add" className="q-btn q-builder-add" aria-describedby={general('fields').length?'builder-fields-error':undefined} onClick={()=>{const uid=nextUid();update(s=>addField(s,uid).schema);focus(`builder-${uid}-label`);}}><ListPlus size={18}/>إضافة سؤال</button>
   <Issues id="builder-fields-error" list={general('fields')}/>
   {warnings.length>0&&<div className="q-callout"><strong>أثر التعديلات على قواعد الحساب</strong><ul>{warnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul></div>}
   {failed==='save'&&error&&<ServerProblem error={error} action="save"/>}
  </div>}
  {!readOnly&&<div className="q-builder-actions">
   <div className="q-builder-state" aria-live="polite">{issues.length?<span className="q-builder-state-error">{count(issues.length)} ملاحظات تمنع الحفظ. <button className="q-inline-link" onClick={()=>focusIssue(issues[0])}>انتقل إلى أولها</button></span>:dirty?<span>تعديلات غير محفوظة</span>:<span>كل التعديلات محفوظة في الخادم</span>}</div>
   <div className="q-builder-buttons">
    <button className="q-btn q-compact q-builder-delete" disabled={busy} onClick={onDelete}><Trash2 size={17}/>حذف النموذج</button>
    <button className="q-btn q-compact" disabled={!dirty||busy} onClick={onDiscard}><RotateCcw size={17}/>تجاهل التعديلات</button>
    <button className="q-btn q-primary" disabled={!dirty||busy||issues.length>0} onClick={onSave}><Save size={18}/>{working==='save'?'جارٍ الحفظ…':'حفظ النموذج'}</button>
   </div>
  </div>}
 </section>;
}

function Issues({id,list}:{id:string;list:SchemaIssue[]}){
 if(!list.length)return null;
 return <div className="q-builder-issues" id={id}>{list.map(issue=><p className="q-field-error" key={issue.message}>{issue.message}</p>)}</div>;
}

type CardProps={field:BuilderField;index:number;total:number;issues:SchemaIssue[];used:boolean;savedOptions:{value:string;label:string}[];neighbour:string|null;update:(change:(schema:BuilderSchema)=>BuilderSchema)=>void;focus:(id:string)=>void};

function QuestionCard({field:f,index,total,issues,used,savedOptions,neighbour,update,focus}:CardProps){
 const base=`builder-${f.uid}`,number=count(index+1);
 const of=(part:SchemaIssue['part'])=>issues.filter(issue=>issue.part===part);
 const invalid=(part:SchemaIssue['part'],hint?:string)=>({'aria-invalid':of(part).length>0,'aria-describedby':[hint,of(part).length?`${base}-${part}-error`:''].filter(Boolean).join(' ')||undefined});
 const patch=(changes:Partial<BuilderField>)=>update(s=>({...s,fields:s.fields.map(x=>x.uid===f.uid?{...x,...changes}:x)}));
 const bound=(key:'min'|'max',raw:string)=>patch({constraints:{...f.constraints,[key]:parseBound(raw)}});
 // Moving a card re-inserts DOM nodes and removing one drops its buttons: keep the keyboard focus on the
 // same control (the other arrow once the card reaches an end), or on the next card after a removal.
 const move=(delta:number)=>{
  const to=index+delta;
  update(s=>{const at=s.fields.findIndex(x=>x.uid===f.uid);return {...s,fields:moveField(s.fields,at,delta)};});
  focus(to<=0?`${base}-down`:to>=total-1?`${base}-up`:`${base}-${delta<0?'up':'down'}`);
 };
 const remove=()=>{update(s=>removeField(s,f.uid));focus(neighbour?`builder-${neighbour}`:'builder-add');};
 return <article className={issues.length?'q-builder-card q-builder-card-invalid':'q-builder-card'} id={base} tabIndex={-1} aria-labelledby={`${base}-heading`}>
  <div className="q-builder-card-top">
   <h3 id={`${base}-heading`}>السؤال {number}</h3>
   {f.fresh&&<span className="q-tag">جديد</span>}
   {used&&<span className="q-tag">تقرؤه قاعدة حساب</span>}
   <div className="q-builder-tools">
    <button id={`${base}-up`} className="q-icon-btn" disabled={index===0} aria-label={`نقل السؤال ${number} إلى الأعلى`} title="نقل إلى الأعلى" onClick={()=>move(-1)}><ArrowUp size={19}/></button>
    <button id={`${base}-down`} className="q-icon-btn" disabled={index===total-1} aria-label={`نقل السؤال ${number} إلى الأسفل`} title="نقل إلى الأسفل" onClick={()=>move(1)}><ArrowDown size={19}/></button>
    <button className="q-icon-btn q-builder-danger" aria-label={`حذف السؤال ${number}`} title="حذف السؤال" onClick={remove}><Trash2 size={19}/></button>
   </div>
  </div>
  <label className="q-field-label">نص السؤال<input id={`${base}-label`} dir="auto" value={f.label} autoComplete="off" placeholder="اكتب السؤال كما سيقرؤه جامع البيانات" {...invalid('label')} onChange={e=>update(s=>setFieldLabel(s,f.uid,e.target.value))}/></label>
  <Issues id={`${base}-label-error`} list={of('label')}/>
  <div className="q-builder-grid">
   <label className="q-field-label">نوع الإجابة<select id={`${base}-type`} value={f.type} onChange={e=>update(s=>setFieldType(s,f.uid,e.target.value as FieldType))}>{Object.entries(fieldTypeLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   <label className="q-field-label">القسم<input id={`${base}-section`} dir="auto" list="builder-sections" value={f.section??''} autoComplete="off" placeholder="اختياري: عنوان يظهر فوق السؤال" onChange={e=>patch({section:e.target.value})}/></label>
  </div>
  <div className="q-builder-checks">
   <label className="q-check-line"><input type="checkbox" checked={!!f.required} onChange={e=>patch({required:e.target.checked})}/>الإجابة مطلوبة</label>
   <label className="q-check-line"><input type="checkbox" checked={!!f.pii} onChange={e=>patch({pii:e.target.checked})}/>بيانات شخصية</label>
   {f.type==='text'&&<label className="q-check-line"><input type="checkbox" checked={!!f.qualitative} onChange={e=>patch({qualitative:e.target.checked})}/>نص مفتوح للتحليل النوعي</label>}
  </div>
  {f.pii&&<p className="q-field-hint q-builder-note"><ShieldCheck size={16}/>لا تُرسل إجابات هذا السؤال إلى الذكاء الاصطناعي، ولا تظهر في التصدير أو في الاقتباسات.{f.qualitative?' لذلك لن يدخل في التحليل النوعي.':''}</p>}
  {f.type==='text'&&f.qualitative&&!f.pii&&<p className="q-field-hint">تُجمع الإجابات النصية لهذا السؤال في محاور يقترحها الذكاء الاصطناعي، وتراجعها أنت.</p>}
  {isSelect(f.type)&&<>
   <label className="q-field-label">الخيارات<textarea id={`${base}-options`} dir="auto" rows={4} value={f.optionsText??optionLines(f.options)} placeholder={'خيار في كل سطر، مثلاً:\nنعم\nلا'} {...invalid('options',`${base}-options-hint`)} onChange={e=>update(s=>setOptionsText(s,f.uid,e.target.value,savedOptions))}/></label>
   <p className="q-field-hint" id={`${base}-options-hint`}>اكتب كل خيار في سطر مستقل · {count(f.options.length)} خيارات.</p>
   <Issues id={`${base}-options-error`} list={of('options')}/>
   {f.options.length>0&&<details className="q-builder-values"><summary>القيم المخزنة للخيارات</summary><ul>{f.options.map(o=><li key={o.value}><span dir="auto">{o.label}</span><bdi>{o.value}</bdi></li>)}</ul><p>تحتفظ الخيارات التي لم يتغيّر نصها بقيمها، فتبقى قواعد الحساب صحيحة.</p></details>}
  </>}
  {isNumeric(f.type)&&<>
   <div className="q-builder-grid q-builder-grid-numbers">
    {/* The number itself as the value (boundValue), so React keeps the typed text ("0.0" on the way to 0.05). */}
    <label className="q-field-label">الحد الأدنى<input id={`${base}-min`} type="number" step="any" dir="ltr" inputMode="decimal" value={boundValue(f.constraints?.min)} {...invalid('constraints')} onChange={e=>bound('min',e.target.value)}/></label>
    <label className="q-field-label">الحد الأعلى<input id={`${base}-max`} type="number" step="any" dir="ltr" inputMode="decimal" value={boundValue(f.constraints?.max)} {...invalid('constraints')} onChange={e=>bound('max',e.target.value)}/></label>
    <label className="q-field-label">الوحدة<input id={`${base}-unit`} dir="auto" value={f.unit??''} autoComplete="off" placeholder="مثلاً: سنة، دينار، ٪" onChange={e=>patch({unit:e.target.value})}/></label>
   </div>
   <Issues id={`${base}-constraints-error`} list={of('constraints')}/>
  </>}
  <div className="q-builder-id">
   {f.fresh?<><label className="q-field-label">معرّف السؤال<input id={`${base}-id`} dir="ltr" value={f.id} autoComplete="off" spellCheck={false} {...invalid('id',`${base}-id-hint`)} onChange={e=>update(s=>setFieldId(s,f.uid,e.target.value))}/></label><p className="q-field-hint" id={`${base}-id-hint`}>أحرف لاتينية صغيرة وأرقام وشرطة سفلية، ويبدأ بحرف. يُقترح من نص السؤال، ويثبت بعد الحفظ.</p></>
   :<p>المعرّف: <bdi>{f.id}</bdi><span className="q-builder-fixed"> · ثابت، تشير إليه قواعد الحساب والإجابات</span></p>}
   <Issues id={`${base}-id-error`} list={of('id')}/>
  </div>
 </article>;
}

function ServerProblem({error,action}:{error:ApiError;action:Action}){
 const lines=error.details.map(item=>arabicDetail(detailText(item)));
 const known=[404,409,422].includes(error.status);
 const title=error.status===409?(action==='delete'?'لا يمكن حذف هذا النموذج: إما أن قاعدة حساب مؤشر تقرأ إجاباته، أو أنه منشور. عدّل قواعد الحساب من صفحة المراجعة أولاً.':'هذا النموذج منشور، ولا يمكن تعديله بعد الآن. أنشئ نموذجاً جديداً بدلاً من ذلك.')
  :error.status===404?'لم يعد هذا النموذج موجوداً في الخادم. حدّث البيانات.'
  :error.status===422?(action==='save'?'رفض الخادم حفظ النموذج. راجع الملاحظات التالية:':'رفض الخادم إنشاء النموذج. راجع الملاحظات التالية:')
  :error.message;
 return <div className="q-callout q-callout-error q-builder-problem" role="alert"><strong dir="auto">{title}</strong>{lines.length>0&&<ul>{lines.map((line,index)=><li key={index} dir="auto">{line}</li>)}</ul>}{known&&<details className="q-builder-server"><summary>رسالة الخادم</summary><p dir="auto">{error.message}</p></details>}</div>;
}

function Preview({schema}:{schema:BuilderSchema}){
 const [answers,setAnswers]=useState<Record<string,unknown>>({});
 const groups=groupBySection(schema.fields),identifier=entityOwner(schema)?.uid;
 return <aside className="q-panel q-builder-preview" aria-labelledby="builder-preview-title">
  <div className="q-builder-preview-head"><h2 id="builder-preview-title"><Eye size={20}/>المعاينة</h2><span className="q-builder-preview-badge">معاينة — لا تُرسل الإجابات</span></div>
  <form className="q-builder-preview-body" noValidate onSubmit={e=>e.preventDefault()} aria-label="معاينة النموذج كما يراه جامع البيانات">
   <div className="q-builder-preview-title"><h3 dir="auto">{schema.title.trim()||'نموذج دون عنوان'}</h3><p>هكذا يظهر النموذج لجامع البيانات. ما تكتبه هنا للتجربة فقط ولا يُحفظ.</p></div>
   {groups.map((group,index)=><section className="q-builder-preview-section" key={index}>{group.section&&<h4 dir="auto">{group.section}</h4>}{group.fields.map(f=>{
    // Keyed by question and type: a trial answer never carries over to another kind of input.
    const slot=`${f.uid}:${f.type}`;
    return <PreviewField key={f.uid} field={f} identifier={identifier===f.uid} value={answers[slot]} onChange={value=>setAnswers(old=>({...old,[slot]:value}))}/>;
   })}</section>)}
   {!schema.fields.length&&<p className="q-inline-empty">أضف سؤالاً لتظهر معاينته هنا.</p>}
   {Object.keys(answers).length>0&&<div className="q-builder-preview-foot"><button type="button" className="q-btn q-compact" onClick={()=>setAnswers({})}><RotateCcw size={16}/>مسح إجابات المعاينة</button></div>}
  </form>
 </aside>;
}

function PreviewField({field:f,identifier,value,onChange}:{field:BuilderField;identifier:boolean;value:unknown;onChange:(value:unknown)=>void}){
 const id=`preview-${f.uid}`,numeric=isNumeric(f.type),min=f.constraints?.min,max=f.constraints?.max;
 const label=<span dir="auto">{f.label.trim()||'سؤال دون نص'}{f.required&&<><span className="q-required" aria-hidden="true"> *</span><span className="q-sr-only"> (مطلوب)</span></>}{numeric&&f.unit?.trim()&&<span className="q-unit"> ({f.unit.trim()})</span>}</span>;
 const notes=<>
  {numeric&&(min!=null||max!=null)&&<p className="q-field-hint">{min!=null&&max!=null?`القيمة بين ${exact(min)} و${exact(max)}.`:min!=null?`القيمة لا تقل عن ${exact(min)}.`:`القيمة لا تزيد على ${exact(max)}.`}</p>}
  {identifier&&<p className="q-field-hint">هذه الإجابة تُعرّف الشخص أو الشيء الذي يخصه السجل.</p>}
  {f.pii&&<p className="q-field-hint"><ShieldCheck size={15}/>بيانات شخصية: لا تُرسل إلى الذكاء الاصطناعي ولا تظهر في التصدير.</p>}
 </>;
 if(isSelect(f.type)){
  const chosen=Array.isArray(value)?value as string[]:[];
  return <div className="q-answer-field"><p className="q-field-label" id={`${id}-label`}>{label}</p>
   {f.options.length?<div className="q-answer-options" role={f.type==='select_one'?'radiogroup':'group'} aria-labelledby={`${id}-label`} aria-required={f.type==='select_one'&&f.required?true:undefined}>{f.options.map(o=><label className="q-answer-option" key={o.value}><input type={f.type==='select_one'?'radio':'checkbox'} name={id} checked={f.type==='select_one'?value===o.value:chosen.includes(o.value)} onChange={e=>onChange(f.type==='select_one'?o.value:e.target.checked?[...chosen,o.value]:chosen.filter(v=>v!==o.value))}/><span dir="auto">{o.label}</span></label>)}</div>
   :<p className="q-field-hint">لم تُضف خيارات لهذا السؤال بعد.</p>}
   {notes}</div>;
 }
 const common={id,name:id,value:String(value??''),'aria-required':f.required||undefined,autoComplete:'off',onChange:(e:{target:{value:string}})=>onChange(e.target.value)};
 return <div className="q-answer-field"><label className="q-field-label" htmlFor={id}>{label}</label>
  {f.type==='text'&&f.qualitative?<textarea {...common} dir="auto"/>
  :<input {...common} dir={f.type==='text'?'auto':'ltr'} type={numeric?'number':f.type==='date'?'date':'text'} step={f.type==='decimal'?'any':numeric?'1':undefined} inputMode={f.type==='decimal'?'decimal':f.type==='integer'?'numeric':undefined} min={numeric&&min!=null?min:undefined} max={numeric&&max!=null?max:undefined}/>}
  {notes}</div>;
}
