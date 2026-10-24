import {useState,Fragment} from 'react';
import {ArrowLeft,Pencil,Check,ShieldCheck,ClipboardCheck,AlertCircle,Trash2,LayoutTemplate,Plus,X,CheckCircle2} from 'lucide-react';
import {useWorkspace} from './Context';
import {Heading,EmptyState,Status,Dialog,OriginBadge,ServerError,count} from './UI';
import {metric,kindLabels,fieldTypeLabels,formsInDefinition,hashParam,sectionGroups} from './model';
import type {IndicatorRow,ResultRow,DefinitionRow,QuestionRow,FormField,PublishResult} from './types';
type Edit={type:'indicator';row:IndicatorRow}|{type:'result';row:ResultRow}|{type:'definition';row:DefinitionRow}|{type:'question';row:QuestionRow};
const sections=[['results','النتائج'],['indicators','المؤشرات'],['forms','النماذج'],['definitions','قواعد الحساب'],['questions','الأسئلة']];
/** The form builder opens the form named in ?form=. */
const builderLink=(key:string)=>`#/forms?form=${encodeURIComponent(key)}`;

export default function Review(){
 const {draft,connected,busy,error,clearError,run,refresh}=useWorkspace();
 const [tab,setTab]=useState(()=>{const wanted=hashParam('tab');return sections.some(([key])=>key===wanted)?wanted as string:'indicators';});
 const [editor,setEditor]=useState<Edit|null>(null),[edited,setEdited]=useState<Record<string,unknown>>({}),[json,setJson]=useState(''),[localError,setLocalError]=useState(''),[publish,setPublish]=useState(false),[removing,setRemoving]=useState<DefinitionRow|null>(null),[result,setResult]=useState<PublishResult|null>(null);

 const formTitles:Record<string,string>=Object.fromEntries(draft.forms.map(f=>[f.key,f.title]));
 const names:Record<string,string>={...formTitles,...Object.fromEntries(draft.indicators.map(i=>[i.id,i.name]))};
 const formsOf=new Map(draft.definitions.map(d=>[d.indicator_id,formsInDefinition(d.definition)]));
 const readers=(key:string)=>draft.definitions.filter(d=>formsOf.get(d.indicator_id)?.includes(key)).map(d=>d.indicator_id);
 const unanswered=draft.open_questions.filter(q=>!q.answer?.trim()),invalid=draft.definitions.filter(d=>d.valid===false);
 // Anything still a draft can be published, also after a first publish (e.g. a form made later in the builder).
 const pendingForms=draft.forms.filter(f=>f.status==='draft'),pendingIndicators=draft.indicators.filter(i=>i.status==='draft'),pendingDefinitions=draft.definitions.filter(d=>d.status==='draft');
 const pending=pendingForms.length+pendingIndicators.length+pendingDefinitions.length>0,published=draft.indicators.some(i=>i.status==='published');
 const withoutRule=pendingIndicators.filter(i=>!formsOf.has(i.id));
 const indicatorName=(id:string|null)=>draft.indicators.find(i=>i.id===id)?.name||'على مستوى الإطار';

 function open(edit:Edit){clearError();setEditor(edit);setEdited(structuredClone(edit.row) as unknown as Record<string,unknown>);setJson(edit.type==='definition'?JSON.stringify(edit.row.definition,null,2):'');setLocalError('');}
 /** A new rule for an indicator that has none: the JSON editor starts from the indicator's kind and the server says what is missing. */
 function addRule(row:IndicatorRow){open({type:'definition',row:{id:'',indicator_id:row.id,definition:{schema_version:1,kind:row.kind||'count'},status:'draft'}});}
 async function save(){if(!editor)return;let path='',body:unknown={},method='PATCH';
  if(editor.type==='indicator'){path=`indicators/${encodeURIComponent(editor.row.id)}`;body=Object.fromEntries(['result_id','code','name','unit','kind','baseline','target','frequency','data_source'].map(key=>[key,edited[key]??null]));}
  if(editor.type==='result'){path=`results/${encodeURIComponent(editor.row.id)}`;body={statement:edited.statement,level_name:edited.level_name,code:edited.code};}
  if(editor.type==='question'){path=`open_questions/${encodeURIComponent(editor.row.id)}`;body={answer:edited.answer||null};}
  if(editor.type==='definition'){path=`definitions/${encodeURIComponent(editor.row.indicator_id)}`;method='PUT';try{body={definition:JSON.parse(json)};}catch{setLocalError('قاعدة الحساب ليست JSON صالحاً. راجع الأقواس والقيم.');return;}}
  const response=await run(api=>api.edit(path,body,method),'تم حفظ التعديلات في الخادم.',{inline:true});if(response!==null){setEditor(null);await refresh();}
 }
 async function removeRule(row:DefinitionRow){const done=await run(api=>api.deleteDefinition(row.indicator_id),'أُزيلت قاعدة الحساب. سيُنشر المؤشر دونها.',{inline:true});if(done){setRemoving(null);await refresh();}}
 async function publishNow(){const response=await run(api=>api.publish(),'تم النشر في الخادم.',{inline:true});if(response){setPublish(false);setResult(response);await refresh();}}

 /** Links to the forms a rule reads; a key with no form in the draft is named as missing. */
 function formLinks(keys:string[],label:string,empty:string){
  return <div className="q-scr-uses"><span>{keys.length?label:empty}</span>{keys.length>0&&<ul>{keys.map(key=><li key={key}>{formTitles[key]?<a className="q-scr-text-link" href={builderLink(key)} dir="auto">{formTitles[key]}</a>:<span className="q-scr-missing"><bdi>{key}</bdi> (نموذج غير موجود في المسودة)</span>}</li>)}</ul>}</div>;
 }

 return <><Heading title="المراجعة والنشر" description="تحقق من التفاصيل. عدّل ما يلزم. ثم ابدأ العمل على إطار معتمد." action={draft.indicators.length?<button className="q-btn q-primary" disabled={!connected||busy||!pending} onClick={()=>{clearError();setPublish(true);}}><Check size={18}/>{!pending?'الإطار منشور':published?'نشر التغييرات الجديدة':'نشر الإطار'}</button>:undefined}/>
 {result&&<div className="q-notice q-scr-result" role="status"><CheckCircle2 size={20} aria-hidden="true"/><div>
  <strong>تم النشر.</strong>
  <p>الإطار المنشور يضم {count(result.indicators)} مؤشرات و{count(result.forms)} نماذج و{count(result.definitions)} قواعد حساب.{result.unanswered_questions>0&&` بقيت ${count(result.unanswered_questions)} أسئلة دون إجابة.`}</p>
  {result.without_definition.length>0&&<><p>نُشرت هذه المؤشرات دون قاعدة حساب، وستظهر «غير قابلة للحساب» حتى تُضاف قاعدتها:</p><ul>{result.without_definition.map(id=><li key={id}>{names[id]?<span dir="auto">{names[id]}</span>:<bdi>{id}</bdi>}</li>)}</ul></>}
  <a className="q-inline-link" href="#/collect">النماذج والبيانات<ArrowLeft size={17}/></a>
 </div><button className="q-icon-btn" onClick={()=>setResult(null)} aria-label="إغلاق ملخص النشر"><X size={18}/></button></div>}
 {!draft.indicators.length?<section className="q-panel"><EmptyState title="لا توجد مسودة للمراجعة" description="بعد استخراج إطارك ستظهر هنا النتائج والمؤشرات والنماذج وقواعد الحساب والأسئلة المفتوحة." icon={<ClipboardCheck size={29}/>}><a className="q-btn q-primary" href="#/framework">رفع إطار النتائج<ArrowLeft size={17}/></a></EmptyState></section>:<>
 <div className="q-review-banner"><ShieldCheck size={28}/><div><h2>{!published?'الذكاء الاصطناعي يقترح، وأنت تقرر':pending?'الإطار منشور، وهناك تغييرات لم تُنشر بعد':'الإطار منشور وجاهز لجمع البيانات'}</h2><p>قواعد الحساب المعتمدة هي التي تنتج الأرقام. يمكنك الرجوع إلى كل مؤشر ونموذج قبل النشر.</p></div><Status value={published?'published':'draft'}/></div>
 {(unanswered.length>0||invalid.length>0||(published&&pending))&&<div className="q-review-alert"><AlertCircle size={21}/><p>{unanswered.length>0&&<span>لديك {count(unanswered.length)} أسئلة لم تُجب بعد. </span>}{invalid.length>0&&<span>تحتاج {count(invalid.length)} قواعد حساب إلى تصحيح قبل النشر. </span>}{published&&pending&&<span>{pendingForms.length>0?`${count(pendingForms.length)} نماذج جديدة لم تُنشر بعد. `:''}انشر التغييرات لتصبح جاهزة للاستخدام.</span>}</p></div>}
 <section className="q-panel"><div className="q-tabs" role="tablist" aria-label="أقسام المراجعة">{sections.map(([key,label])=>{const rows=key==='questions'?draft.open_questions:draft[key as 'results'|'indicators'|'forms'|'definitions'];return <button role="tab" aria-selected={tab===key} key={key} onClick={()=>setTab(key)}>{label}<span className="q-tab-count">{count(rows.length)}</span></button>;})}</div>
 <div className="q-review-content">
 {tab==='results'&&draft.results.map(row=><article className="q-review-row" key={row.id}><div className="q-review-row-top"><span className="q-tag" dir="auto">{row.level_name}</span><button className="q-btn q-compact" disabled={busy} onClick={()=>open({type:'result',row})}><Pencil size={16}/>تعديل</button></div><h3 dir="auto">{row.statement}</h3><dl className="q-review-meta"><div><dt>الرمز</dt><dd><bdi>{row.code||'غير محدد'}</bdi></dd></div><div><dt>النتيجة الأعلى</dt><dd dir="auto">{draft.results.find(r=>r.id===row.parent_id)?.statement||'نتيجة رئيسية'}</dd></div></dl></article>)}

 {tab==='indicators'&&draft.indicators.map(row=><article className="q-review-row" key={row.id}>
  <div className="q-review-row-top"><Status value={row.status}/><div className="q-scr-row-actions">{!formsOf.has(row.id)&&<button className="q-btn q-compact" disabled={busy} onClick={()=>addRule(row)}><Plus size={16}/>إضافة قاعدة حساب</button>}<button className="q-btn q-compact" disabled={busy} onClick={()=>open({type:'indicator',row})}><Pencil size={16}/>تعديل المؤشر</button></div></div>
  <h3 dir="auto">{row.name}</h3><p dir="auto">{draft.results.find(r=>r.id===row.result_id)?.statement||'غير مرتبط بنتيجة'}</p>
  <dl className="q-review-meta">{[['نوع الحساب',kindLabels[row.kind||'']||row.kind||'غير محدد'],['الوحدة',row.unit||'غير محددة'],['خط الأساس',metric(row.baseline,row.unit)],['المستهدف',metric(row.target,row.unit)],['دورية القياس',row.frequency||'غير محددة'],['مصدر البيانات',row.data_source||'غير محدد']].map(([label,value])=><div key={label}><dt>{label}</dt><dd dir="auto">{value}</dd></div>)}</dl>
  {formsOf.has(row.id)?formLinks(formsOf.get(row.id)||[],'النماذج التي تغذّيه:','لا تقرأ قاعدة حسابه أي نموذج.'):<p className="q-scr-uses">{row.status==='published'?'لا توجد قاعدة حساب لهذا المؤشر، لذا يظهر «غير قابل للحساب» في لوحة المتابعة.':'لا توجد قاعدة حساب لهذا المؤشر، لذا سيظهر «غير قابل للحساب» بعد النشر.'}</p>}
 </article>)}

 {tab==='forms'&&(draft.forms.length?draft.forms.map(row=>{const users=readers(row.key);return <article className="q-review-row" key={row.key}>
  <div className="q-review-row-top"><div className="q-scr-badges"><Status value={row.status}/><OriginBadge origin={row.schema.origin} source={row.schema.source}/></div><a className="q-btn q-compact" href={builderLink(row.key)}>{row.status==='draft'?<><Pencil size={16}/>تعديل في منشئ النماذج</>:<><LayoutTemplate size={16}/>عرض في منشئ النماذج</>}</a></div>
  <h3 dir="auto">{row.title}</h3>
  <p>{count(row.schema.fields.length)} أسئلة · مفتاح النموذج: <bdi>{row.key}</bdi>{row.schema.source&&<> · المصدر: <bdi>{row.schema.source}</bdi></>}</p>
  <div className="q-scr-uses"><span>{users.length?`يغذّي ${count(users.length)} مؤشرات:`:'لا يغذّي أي مؤشر بعد: لا تقرؤه أي قاعدة حساب.'}</span>{users.length>0&&<ul>{users.map(id=><li key={id}>{names[id]?<span dir="auto">{names[id]}</span>:<bdi>{id}</bdi>}</li>)}</ul>}</div>
  <Questions fields={row.schema.fields}/>
 </article>;}):<EmptyState title="لا توجد نماذج في المسودة" description="ليس كل مؤشر بحاجة إلى مسح. راجع مصدر البيانات وطريقة جمعها ضمن المؤشرات."><a className="q-btn" href="#/forms">منشئ النماذج<ArrowLeft size={17}/></a></EmptyState>)}

 {tab==='definitions'&&(draft.definitions.length?draft.definitions.map(row=>{const indicator=draft.indicators.find(i=>i.id===row.indicator_id);return <article className="q-review-row" key={row.id}>
  <div className="q-review-row-top"><div className="q-scr-badges"><span className={`q-status ${row.valid===false?'q-status-failed':'q-status-ok'}`}><i/>{row.valid===false?'تحتاج إلى تصحيح':'صالحة بنيوياً'}</span><Status value={row.status}/></div><div className="q-scr-row-actions">{indicator?.status==='draft'&&row.status==='draft'&&<button className="q-btn q-compact" disabled={busy} onClick={()=>{clearError();setRemoving(row);}}><Trash2 size={16}/>إزالة القاعدة</button>}<button className="q-btn q-compact" disabled={busy} onClick={()=>open({type:'definition',row})}><Pencil size={16}/>تعديل القاعدة</button></div></div>
  <h3 dir="auto">{indicator?indicator.name:<>مؤشر غير موجود في المسودة: <bdi>{row.indicator_id}</bdi></>}</h3>
  <p>نوع الحساب: {kindLabels[String(row.definition.kind)]||String(row.definition.kind||'غير محدد')}</p>
  {formLinks(formsOf.get(row.indicator_id)||[],'تقرأ من النماذج:','لا تقرأ هذه القاعدة أي نموذج.')}
  {row.errors?.length?<ul className="q-field-error">{row.errors.map((item,index)=><li dir="auto" key={index}>{item}</li>)}</ul>:null}
  <details className="q-technical"><summary>تفاصيل القاعدة وارتباط الحقول</summary><pre dir="ltr">{JSON.stringify(row.definition,null,2)}</pre></details>
 </article>;}):<EmptyState title="لا توجد قواعد حساب بعد" description="المؤشرات التي لا تملك تعريفاً معتمداً ستعرض سبب تعذر الحساب بدلاً من قيمة مفترضة."/>)}

 {tab==='questions'&&(draft.open_questions.length?draft.open_questions.map(row=><article className="q-review-row" key={row.id}><div className="q-review-row-top"><span className={`q-status ${row.answer?'q-status-ok':''}`}>{row.answer?'تمت الإجابة':'بانتظار إجابة'}</span><button className="q-btn q-compact" disabled={busy} onClick={()=>open({type:'question',row})}><Pencil size={16}/>{row.answer?'تعديل الإجابة':'إضافة إجابة'}</button></div><h3 dir="auto">{row.question}</h3><p dir="auto">{indicatorName(row.indicator_id)}</p>{row.answer&&<blockquote dir="auto" className="q-saved-answer">{row.answer}</blockquote>}</article>):<EmptyState title="لا توجد أسئلة مفتوحة" description="راجع بقية التفاصيل ثم انشر الإطار عندما تكون مستعداً."/>)}
 </div></section><div className="q-review-footer"><p>النماذج المنشورة تصبح جاهزة للجمع، ولا يمكن تعديل بنيتها بعد النشر في النسخة الحالية.</p><a href="#/collect" className="q-inline-link">النماذج والبيانات<ArrowLeft size={17}/></a></div></>}

 {editor&&<Dialog title={editor.type==='indicator'?'تعديل المؤشر':editor.type==='result'?'تعديل النتيجة':editor.type==='definition'?(editor.row.id?'تعديل قاعدة الحساب':'إضافة قاعدة حساب'):'الإجابة عن السؤال'} onClose={()=>{if(!busy)setEditor(null);}} wide><form onSubmit={e=>{e.preventDefault();save();}}>
 {editor.type==='indicator'&&<><label className="q-field-label">اسم المؤشر<input required name="indicator-name" dir="auto" value={String(edited.name??'')} onChange={e=>setEdited({...edited,name:e.target.value})}/></label><div className="q-two-col"><label className="q-field-label">نوع الحساب<select value={String(edited.kind||'')} onChange={e=>setEdited({...edited,kind:e.target.value||null})}><option value="">غير محدد</option>{Object.entries(kindLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label className="q-field-label">الوحدة<input name="unit" dir="auto" value={String(edited.unit??'')} onChange={e=>setEdited({...edited,unit:e.target.value})}/></label>{[['baseline','خط الأساس'],['target','المستهدف']].map(([key,label])=><label className="q-field-label" key={key}>{label}<input type="number" step="any" name={key} value={edited[key]==null?'':String(edited[key])} onChange={e=>setEdited({...edited,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>)}</div><label className="q-field-label">النتيجة المرتبطة<select value={String(edited.result_id||'')} onChange={e=>setEdited({...edited,result_id:e.target.value||null})}><option value="">دون ارتباط</option>{draft.results.map(r=><option key={r.id} value={r.id}>{r.statement}</option>)}</select></label><div className="q-two-col">{[['code','الرمز'],['frequency','دورية القياس'],['data_source','مصدر البيانات']].map(([key,label])=><label className="q-field-label" key={key}>{label}<input name={key} dir="auto" value={String(edited[key]??'')} onChange={e=>setEdited({...edited,[key]:e.target.value})}/></label>)}</div></>}
 {editor.type==='result'&&<>{[['statement','نص النتيجة'],['level_name','مستوى النتيجة'],['code','الرمز']].map(([key,label])=><label className="q-field-label" key={key}>{label}<input required={key!=='code'} name={key} dir="auto" value={String(edited[key]??'')} onChange={e=>setEdited({...edited,[key]:e.target.value})}/></label>)}</>}
 {editor.type==='question'&&<><h3 className="q-detail-title" dir="auto">{editor.row.question}</h3><label className="q-field-label">الإجابة<textarea name="answer" dir="auto" value={String(edited.answer||'')} onChange={e=>setEdited({...edited,answer:e.target.value})}/></label></>}
 {editor.type==='definition'&&<><p className="q-dialog-intro" dir="auto">{indicatorName(editor.row.indicator_id)}</p><p className="q-field-hint">تُفحص القاعدة بواسطة الخادم قبل اعتمادها. حافظ على مفاتيح النماذج ومعرّفات الحقول الفعلية.{draft.forms.length>0&&<> مفاتيح النماذج المتاحة: {draft.forms.map((f,index)=><Fragment key={f.key}>{index>0&&'، '}<bdi>{f.key}</bdi></Fragment>)}.</>}</p><label className="q-field-label">قاعدة الحساب (JSON)<textarea className="q-json-editor" dir="ltr" value={json} onChange={e=>setJson(e.target.value)} spellCheck={false}/></label></>}
 {localError&&<p className="q-field-error" role="alert">{localError}</p>}<ServerError error={error} names={names}/><div className="q-dialog-actions"><button className="q-btn" type="button" disabled={busy} onClick={()=>setEditor(null)}>إلغاء</button><button className="q-btn q-primary" disabled={busy}><Check size={18}/>{busy?'جارٍ الحفظ…':'حفظ التعديلات'}</button></div></form></Dialog>}

 {removing&&<Dialog title="إزالة قاعدة الحساب" onClose={()=>{if(!busy)setRemoving(null);}}>
  <p className="q-dialog-intro">ستُزال قاعدة حساب المؤشر «<span dir="auto">{indicatorName(removing.indicator_id)}</span>».</p>
  <div className="q-callout">سيُنشر هذا المؤشر دون قاعدة حساب، ويظهر في لوحة المتابعة «غير قابل للحساب» حتى تضيف له قاعدة جديدة من قسم المؤشرات. لا يُحذف المؤشر نفسه.</div>
  <ServerError error={error} names={names}/>
  <div className="q-dialog-actions"><button className="q-btn" type="button" disabled={busy} onClick={()=>setRemoving(null)}>إلغاء</button><button className="q-btn q-primary" type="button" disabled={busy} onClick={()=>removeRule(removing)}><Trash2 size={18}/>{busy?'جارٍ الإزالة…':'إزالة القاعدة'}</button></div>
 </Dialog>}

 {publish&&<Dialog title={published?'نشر التغييرات الجديدة':'نشر إطار النتائج'} onClose={()=>{if(!busy)setPublish(false);}}>
  <p className="q-dialog-intro">{published?'سيُنشر ما لم يُنشر بعد، ولا يتغير ما نُشر سابقاً:':'سيُنشر ما يلي، ويبدأ جمع البيانات بعد النشر:'}</p>
  <ul className="q-scr-publish-list">{pendingIndicators.length>0&&<li>{count(pendingIndicators.length)} مؤشرات</li>}{pendingForms.length>0&&<li>{count(pendingForms.length)} نماذج{published&&<>: {pendingForms.map((f,index)=><Fragment key={f.key}>{index>0&&'، '}<span dir="auto">{f.title}</span></Fragment>)}</>}</li>}{pendingDefinitions.length>0&&<li>{count(pendingDefinitions.length)} قواعد حساب</li>}</ul>
  {withoutRule.length>0&&<div className="q-callout"><strong>{count(withoutRule.length)} مؤشرات ستُنشر دون قاعدة حساب، وستظهر «غير قابلة للحساب»:</strong><ul className="q-scr-details">{withoutRule.map(i=><li key={i.id} dir="auto">{i.name}</li>)}</ul></div>}
  {unanswered.length>0&&<div className="q-callout">لديك {count(unanswered.length)} أسئلة دون إجابة. راجع أثرها على تعريف المؤشرات قبل المتابعة.</div>}
  {invalid.length>0&&<div className="q-callout q-callout-error">قواعد الحساب غير الصالحة ستمنع النشر. صحّحها من قسم قواعد الحساب.</div>}
  <ServerError error={error} names={names}/>
  <div className="q-dialog-actions"><button className="q-btn" type="button" disabled={busy} onClick={()=>setPublish(false)}>العودة للمراجعة</button><button className="q-btn q-primary" type="button" disabled={busy} onClick={publishNow}><Check size={18}/>{busy?'جارٍ النشر…':published?'نشر التغييرات':'نشر الإطار'}</button></div>
 </Dialog>}
 </>;
}

/** The questions of a form, read-only and grouped by section. Changes are made in the form builder. */
function Questions({fields}:{fields:FormField[]}){
 return <details className="q-form-questions"><summary>عرض الأسئلة والخيارات</summary>{sectionGroups(fields).map((group,index)=><Fragment key={index}>
  {group.section&&<h4 className="q-scr-question-section" dir="auto">{group.section}</h4>}
  {group.fields.map(field=><div key={field.id}>
   <strong dir="auto">{field.label}{field.required&&<span className="q-required"> *</span>}</strong>
   <p>{fieldTypeLabels[field.type]||field.type}{field.unit&&<> · <bdi>{field.unit}</bdi></>} · <bdi>{field.id}</bdi>{field.pii&&' · بيانات شخصية'}{field.qualitative&&' · سؤال نوعي'}</p>
   {field.options.length>0&&<p dir="auto">{field.options.map(o=>o.label).join(' / ')}</p>}
   {field.constraints&&(field.constraints.min!=null||field.constraints.max!=null)&&<p>الحد الأدنى: {metric(field.constraints.min)} · الحد الأعلى: {metric(field.constraints.max)}</p>}
  </div>)}
 </Fragment>)}</details>;
}
