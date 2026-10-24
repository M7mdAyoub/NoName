import {describe,it,expect,vi} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Forms from '../workspace/Forms';
import {FIELD_ID,slug,newFieldId,optionsFromLines,cleanSchema,toBuilder,moveField,addField,changeType,setFieldType,setFieldLabel,setFieldId,setEntity,setOptionsText,removeField,parseBound,boundValue,validateFormSchema,groupBySection,rulesReading,arabicDetail} from '../workspace/builder';
import type {BuilderField} from '../workspace/builder';
import type {FormField,FormSchema} from '../workspace/types';

const field=(id:string,changes:Partial<FormField>={}):FormField=>({id,type:'text',label:`سؤال ${id}`,required:false,options:[],...changes});
const schema=(fields:FormField[],changes:Partial<FormSchema>={}):FormSchema=>({schema_version:1,title:'مسح المستفيدين',fields,...changes});
const parts=(s:FormSchema)=>validateFormSchema(s).map(issue=>[issue.field,issue.part]);

describe('field ids',()=>{
 it('slugifies Latin letters and digits and ignores Arabic',()=>{
  expect(slug('Phone Number')).toBe('phone_number');
  expect(slug('  Âge (years) ')).toBe('age_years');
  expect(slug('عدد المستفيدين')).toBe('');
  expect(slug('عدد الأسر (households)')).toBe('households');
 });
 it('falls back to q_1, q_2 … for Arabic labels and never repeats an id',()=>{
  expect(newFieldId('الاسم الكامل',[])).toBe('q_1');
  expect(newFieldId('الجنس',['q_1'])).toBe('q_2');
  expect(newFieldId('العمر',['q_2'])).toBe('q_1');
  expect(newFieldId('',['q_1','q_2','q_3'])).toBe('q_4');
 });
 it('keeps Latin slugs unique and always valid on the server',()=>{
  expect(newFieldId('Age',[])).toBe('age');
  expect(newFieldId('Age',['age'])).toBe('age_2');
  expect(newFieldId('Age',['age','age_2'])).toBe('age_3');
  expect(newFieldId('2024 visits',[])).toBe('q_2024_visits');
  const long=newFieldId('x'.repeat(200),['x'.repeat(40)]);
  for(const id of [long,newFieldId('2024 visits',[]),newFieldId('سؤال',[]),newFieldId('Ünïcödé — text!',[])])expect(id).toMatch(FIELD_ID);
 });
});

describe('options from lines',()=>{
 it('makes one option per non-empty line, with opt_N values for Arabic labels',()=>{
  expect(optionsFromLines('نعم\n\n  لا  \n')).toEqual([{value:'opt_1',label:'نعم'},{value:'opt_2',label:'لا'}]);
  expect(optionsFromLines('Yes\r\nNo')).toEqual([{value:'yes',label:'Yes'},{value:'no',label:'No'}]);
 });
 it('keeps the earlier value of an unchanged label, even after reordering',()=>{
  const previous=[{value:'female',label:'أنثى'},{value:'male',label:'ذكر'}];
  expect(optionsFromLines('ذكر\nأنثى\nغير ذلك',previous)).toEqual([{value:'male',label:'ذكر'},{value:'female',label:'أنثى'},{value:'opt_1',label:'غير ذلك'}]);
 });
 it('gives a changed label a new value',()=>{
  expect(optionsFromLines('Yes please\nNo',[{value:'y',label:'Yes'},{value:'n',label:'No'}])).toEqual([{value:'yes_please',label:'Yes please'},{value:'n',label:'No'}]);
 });
 it('never produces duplicate values',()=>{
  const repeated=optionsFromLines('نعم\nنعم\nYes\nyes\nYES',[{value:'yes',label:'Yes'}]);
  expect(repeated.map(o=>o.value)).toEqual(['opt_1','opt_2','yes','yes_2','yes_3']);
  const clash=optionsFromLines('جديد\nقديم',[{value:'opt_1',label:'قديم'}]);
  expect(clash).toEqual([{value:'opt_2',label:'جديد'},{value:'opt_1',label:'قديم'}]);
  const twice=optionsFromLines('Male\nMale',[{value:'m',label:'Male'},{value:'m',label:'Male'}]);
  expect(new Set(twice.map(o=>o.value)).size).toBe(2);
  expect(twice[0].value).toBe('m');
 });
 it('prefers the saved value when the text is edited and restored',()=>{
  let s=toBuilder(schema([field('sex',{type:'select_one',options:[{value:'m',label:'Male'},{value:'f',label:'Female'}]})]));
  const uid=s.fields[0].uid,saved=s.fields[0].options;
  s=setOptionsText(s,uid,'Mal\nFemale',saved);
  expect(s.fields[0].options.map(o=>o.value)).toEqual(['mal','f']);
  s=setOptionsText(s,uid,'Male\nFemale',saved);
  expect(s.fields[0].options.map(o=>o.value)).toEqual(['m','f']);
  expect(s.fields[0].optionsText).toBe('Male\nFemale');
 });
 it('never gives a new option the value of a saved option that was removed or renamed',()=>{
  // A rule reading "opt_2" (لا) must not silently start counting another answer.
  const saved=[{value:'opt_1',label:'نعم'},{value:'opt_2',label:'لا'},{value:'opt_3',label:'لا أعرف'}];
  expect(optionsFromLines('نعم\nلا أعرف\nأحياناً',saved)).toEqual([{value:'opt_1',label:'نعم'},{value:'opt_3',label:'لا أعرف'},{value:'opt_4',label:'أحياناً'}]);
  expect(optionsFromLines('كلا\nأجل',saved.slice(0,2)).map(o=>o.value)).toEqual(['opt_3','opt_4']);
  expect(optionsFromLines('Yes\nNO',[{value:'yes',label:'Yes'},{value:'no',label:'No'}])).toEqual([{value:'yes',label:'Yes'},{value:'no_2',label:'NO'}]);
  // Typed one key at a time in the builder: the removed option is reported, its value is not reused.
  let s=toBuilder(schema([field('answer',{type:'select_one',options:saved})]));
  const uid=s.fields[0].uid;
  for(const text of ['نعم\nل\nلا أعرف','نعم\n\nلا أعرف','نعم\nلا أعرف',...[...'أحياناً'].map((_,i,all)=>'نعم\nلا أعرف\n'+all.slice(0,i+1).join(''))])s=setOptionsText(s,uid,text,saved);
  const now=s.fields[0].options;
  expect(now.map(o=>o.label)).toEqual(['نعم','لا أعرف','أحياناً']);
  expect(now.slice(0,2).map(o=>o.value)).toEqual(['opt_1','opt_3']);
  expect(saved.map(o=>o.value)).not.toContain(now[2].value);
  expect(saved.filter(o=>!now.some(option=>option.value===o.value)).map(o=>o.label)).toEqual(['لا']);
  // Restoring the label brings its saved value back.
  s=setOptionsText(s,uid,'نعم\nلا\nلا أعرف',saved);
  expect(s.fields[0].options.map(o=>o.value)).toEqual(['opt_1','opt_2','opt_3']);
 });
});

describe('clean schema',()=>{
 it('strips builder state and drops what a type cannot have',()=>{
  const builder=toBuilder(schema([
   field('age',{type:'integer',unit:' سنة ',constraints:{min:0,max:null}}),
   field('notes',{qualitative:true,pii:true,section:'  '}),
   field('visit',{type:'date',unit:'يوم',constraints:{min:null,max:null},qualitative:true}),
   field('sex',{type:'select_one',label:' الجنس ',options:[{value:'f',label:' أنثى'},{value:'m',label:'ذكر'}],section:' البيانات العامة '}),
  ],{title:'  مسح  ',entity_key_field:'age',origin:'document',source:'survey.xlsx > Sheet1'}));
  const clean=cleanSchema(builder);
  expect(clean).toEqual({schema_version:1,title:'مسح',entity_key_field:'age',origin:'document',source:'survey.xlsx > Sheet1',fields:[
   {id:'age',type:'integer',label:'سؤال age',required:false,options:[],unit:'سنة',constraints:{min:0},pii:false,qualitative:false,section:null},
   {id:'notes',type:'text',label:'سؤال notes',required:false,options:[],unit:null,constraints:null,pii:true,qualitative:true,section:null},
   {id:'visit',type:'date',label:'سؤال visit',required:false,options:[],unit:null,constraints:null,pii:false,qualitative:false,section:null},
   {id:'sex',type:'select_one',label:'الجنس',required:false,options:[{value:'f',label:'أنثى'},{value:'m',label:'ذكر'}],unit:null,constraints:null,pii:false,qualitative:false,section:'البيانات العامة'},
  ]});
  expect(JSON.stringify(clean)).not.toMatch(/uid|fresh|autoId|optionsText/);
 });
 it('keeps missing origin and source as null and clears an empty identifier',()=>{
  const clean=cleanSchema({title:'نموذج',entity_key_field:'',fields:[field('a')]});
  expect([clean.origin,clean.source,clean.entity_key_field]).toEqual([null,null,null]);
 });
 it('is stable: cleaning a clean schema changes nothing',()=>{
  const once=cleanSchema(toBuilder(schema([field('a',{type:'decimal',constraints:{min:1.5,max:9}})])));
  expect(cleanSchema(once)).toEqual(once);
 });
});

describe('editing operations',()=>{
 it('moves a question up or down and ignores impossible moves',()=>{
  expect(moveField(['a','b','c'],2,-1)).toEqual(['a','c','b']);
  expect(moveField(['a','b','c'],0,1)).toEqual(['b','a','c']);
  expect(moveField(['a','b','c'],0,-1)).toEqual(['a','b','c']);
  expect(moveField(['a','b','c'],2,1)).toEqual(['a','b','c']);
 });
 it('adds a new question with a free id that follows its label until typed',()=>{
  const start=toBuilder(schema([field('q_1')]));
  const {schema:added,uid}=addField(start);
  const created=added.fields.find(f=>f.uid===uid)!;
  expect(created).toMatchObject({id:'q_2',type:'text',label:'',fresh:true,autoId:true});
  let s=setFieldLabel(added,uid,'Household size');
  expect(s.fields[1].id).toBe('household_size');
  s=setFieldLabel(s,uid,'حجم الأسرة');
  expect(s.fields[1].id).toBe('q_2');
  s=setFieldId(s,uid,'hh_size');
  s=setFieldLabel(s,uid,'Household size');
  expect(s.fields[1].id).toBe('hh_size');
 });
 it('never gives a new question the id of a saved question, even a removed one, or one a rule reads',()=>{
  let s=toBuilder(schema([field('q_1'),field('q_2'),field('q_3')]),[],['q_4']);
  expect(s.reserved).toEqual(['q_1','q_2','q_3','q_4']);
  s=removeField(s,s.fields[1].uid);
  const {schema:added,uid}=addField(s);
  const id=(t:typeof added)=>t.fields.find(f=>f.uid===uid)!.id;
  expect(id(added)).toBe('q_5');
  expect(id(setFieldLabel(added,uid,'عدد الزيارات'))).toBe('q_5');
  expect(id(setFieldLabel(added,uid,'Q 2'))).toBe('q_2_2');
  expect(cleanSchema(added)).not.toHaveProperty('reserved');
 });
 it('never renames a saved question',()=>{
  const s=toBuilder(schema([field('respondent')]));
  const uid=s.fields[0].uid;
  expect(setFieldId(s,uid,'other').fields[0].id).toBe('respondent');
  expect(setFieldLabel(s,uid,'Name').fields[0].id).toBe('respondent');
 });
 it('clears options, constraints, unit and qualitative when the type no longer allows them',()=>{
  const select:BuilderField={...field('x',{type:'select_one',options:[{value:'a',label:'أ'},{value:'b',label:'ب'}]}),uid:'u',optionsText:'أ\nب'};
  expect(changeType(select,'select_multiple').options).toHaveLength(2);
  expect(changeType(select,'text')).toMatchObject({options:[],optionsText:''});
  const number:BuilderField={...field('n',{type:'integer',unit:'%',constraints:{min:0,max:100}}),uid:'v'};
  expect(changeType(number,'decimal')).toMatchObject({unit:'%',constraints:{min:0,max:100}});
  expect(changeType(number,'date')).toMatchObject({unit:null,constraints:null});
  const open:BuilderField={...field('t',{qualitative:true}),uid:'w'};
  expect(changeType(open,'integer').qualitative).toBe(false);
 });
 it('keeps the identifier question consistent with renames, type changes and removals',()=>{
  let s=toBuilder(schema([field('name')],{entity_key_field:'name'}));
  expect(setFieldType(s,s.fields[0].uid,'integer').entity_key_field).toBe('name');
  expect(setFieldType(s,s.fields[0].uid,'date').entity_key_field).toBeNull();
  expect(removeField(s,s.fields[0].uid)).toMatchObject({fields:[],entity_key_field:null});
  const {schema:added,uid}=addField({...s,entity_key_field:null});
  s=setFieldId({...added,entity_key_field:added.fields[1].id},uid,'beneficiary_id');
  expect(s.entity_key_field).toBe('beneficiary_id');
 });
 it('never moves the identifier to a new question whose typed id passes through the identifier id',()=>{
  // A form from an Arabic document: the identifier question has the id "q".
  const start=toBuilder(schema([field('q',{label:'رقم المستفيد'}),field('q_2')],{entity_key_field:'q'}));
  const {schema:empty,uid}=addField(start),added=setFieldLabel(empty,uid,'المؤهل العلمي');
  const type=(s:typeof added,ids:string[])=>{for(const id of ids){s=setFieldId(s,uid,id);expect(s.entity_key_field).toBe('q');}return s;};
  const prefixes=(text:string)=>[...text].map((_,i)=>text.slice(0,i+1));
  let s=type(added,prefixes('qualification'));
  expect(validateFormSchema(cleanSchema(s))).toEqual([]);
  // The suggested id q_1 erased key by key, then another id typed.
  s=type(added,['q_','q','',...prefixes('edu')]);
  expect(cleanSchema(s).entity_key_field).toBe('q');
  // The same when the new question was moved above the identifier question.
  type({...added,fields:moveField(added.fields,2,-2)},prefixes('qualification'));
  // Removing, or changing the type of, the new question that shares the id keeps the identifier.
  const twin=setFieldId(added,uid,'q');
  expect(removeField(twin,uid).entity_key_field).toBe('q');
  expect(setFieldType(twin,uid,'date').entity_key_field).toBe('q');
  // Removing the identifier question itself clears it: it does not pass to the twin.
  expect(removeField(twin,twin.fields[0].uid).entity_key_field).toBeNull();
  expect(setFieldType(twin,twin.fields[0].uid,'date').entity_key_field).toBeNull();
 });
 it('keeps a new identifier question as the identifier while its id is typed through a saved id',()=>{
  const {schema:added,uid}=addField(toBuilder(schema([field('q'),field('name')])));
  let s=setEntity(added,added.fields[2].id);
  for(const id of ['q','qi','qid'])s=setFieldId(s,uid,id);
  expect(s.entity_key_field).toBe('qid');
  expect(setEntity(s,'name').entity_key_field).toBe('name');
  expect(setEntity(s,null).entity_key_field).toBeNull();
 });
});

describe('min and max inputs',()=>{
 // Typing into a controlled <input type="number">: the browser reports text that is not a number yet
 // ("0.", "-", "1e") as "", and React rewrites the text when `input.value != value` (react-dom updateInput).
 const number=/^-?(\d+(\.\d+)?|\.\d+)(e[-+]?\d+)?$/i;
 function type(keys:string,shown:(value:number|null)=>string|number=boundValue){
  let text='',bound:number|null=null;
  for(const key of [...keys]){
   text=key==='⌫'?text.slice(0,-1):text+key;
   const reported=number.test(text)?text:'';
   bound=parseBound(reported);
   const value=shown(bound);
   if((value===0&&reported==='')||(reported as unknown)!=value)text=String(value);
  }
  return {text,bound};
 }
 it('keeps what the person types',()=>{
  expect(type('0.05')).toEqual({text:'0.05',bound:0.05});
  expect(type('1.05')).toEqual({text:'1.05',bound:1.05});
  expect(type('-1')).toEqual({text:'-1',bound:-1});
  expect(type('-0.5')).toEqual({text:'-0.5',bound:-0.5});
  expect(type('1e3')).toEqual({text:'1e3',bound:1000});
  expect(type('12⌫⌫')).toEqual({text:'',bound:null});
  // The text of the number, as before, turned 0.05 into 5 and -0.5 into 0.5.
  const asText=(value:number|null)=>value==null?'':String(value);
  expect(type('0.05',asText)).toEqual({text:'5',bound:5});
  expect(type('-0.5',asText)).toEqual({text:'0.5',bound:0.5});
 });
 it('reads an empty or non-numeric text as no bound',()=>{
  expect([parseBound(''),parseBound(' '),parseBound('abc'),parseBound('1e400'),parseBound('0'),parseBound('-2.5')]).toEqual([null,null,null,null,0,-2.5]);
  expect([boundValue(null),boundValue(undefined),boundValue(0)]).toEqual(['','',0]);
 });
});

describe('validation mirrors the server rules',()=>{
 it('accepts a valid form',()=>{
  expect(validateFormSchema(schema([field('name'),field('sex',{type:'select_one',options:[{value:'f',label:'أنثى'},{value:'m',label:'ذكر'}]}),field('age',{type:'integer',constraints:{min:0,max:120}})],{entity_key_field:'name'}))).toEqual([]);
 });
 it('needs a title and at least one question',()=>{
  expect(parts(schema([],{title:'  '}))).toEqual([[null,'title'],[null,'fields']]);
 });
 it('checks the id pattern and uniqueness',()=>{
  for(const id of ['Name','1st','_x','الاسم','a-b','a'.repeat(64),''])expect(parts(schema([field(id)]))).toEqual([[0,'id']]);
  expect(parts(schema([field('a'.repeat(63))]))).toEqual([]);
  expect(parts(schema([field('a'),field('b'),field('a')]))).toEqual([[2,'id']]);
 });
 it('needs a label',()=>{
  expect(parts(schema([field('a',{label:'   '})]))).toEqual([[0,'label']]);
 });
 it('needs two options with unique values on select questions, and options only there',()=>{
  expect(parts(schema([field('a',{type:'select_multiple',options:[{value:'x',label:'س'}]})]))).toEqual([[0,'options']]);
  expect(parts(schema([field('a',{type:'select_one',options:[{value:'x',label:'س'},{value:'x',label:'ص'}]})]))).toEqual([[0,'options']]);
  expect(parts(schema([field('a',{options:[{value:'x',label:'س'},{value:'y',label:'ص'}]})]))).toEqual([[0,'options']]);
 });
 it('allows min and max only on numeric questions, in order',()=>{
  expect(parts(schema([field('a',{constraints:{min:1}})]))).toEqual([[0,'constraints']]);
  expect(parts(schema([field('a',{type:'decimal',constraints:{min:5,max:1}})]))).toEqual([[0,'constraints']]);
  expect(parts(schema([field('a',{type:'decimal',constraints:{min:null,max:null}})]))).toEqual([]);
 });
 it('needs the identifier to be an existing text or integer question',()=>{
  expect(parts(schema([field('a')],{entity_key_field:'missing'}))).toEqual([[null,'entity']]);
  expect(parts(schema([field('a',{type:'date'})],{entity_key_field:'a'}))).toEqual([[null,'entity']]);
  expect(parts(schema([field('a',{type:'integer'})],{entity_key_field:'a'}))).toEqual([]);
 });
 it('writes every message in Arabic',()=>{
  const all=validateFormSchema(schema([field('Bad',{label:'',constraints:{min:1}}),field('Bad',{type:'select_one'})],{title:'',entity_key_field:'zzz'}));
  expect(all.length).toBeGreaterThanOrEqual(7);
  for(const issue of all)expect(issue.message).toMatch(/[؀-ۿ]/);
 });
});

describe('preview and rules',()=>{
 it('groups consecutive questions by section',()=>{
  const groups=groupBySection([{id:'a',section:'أ'},{id:'b',section:' أ '},{id:'c',section:null},{id:'d',section:''},{id:'e',section:'أ'}]);
  expect(groups.map(g=>[g.section,g.fields.map(f=>f.id).join('')])).toEqual([['أ','ab'],[null,'cd'],['أ','e']]);
  expect(groupBySection([])).toEqual([]);
 });
 it('finds the indicators, fields and identifier a form feeds',()=>{
  const definitions=[
   {indicator_id:'i1',definition:{kind:'count',count:{form:'survey',unit:'entity',where:{all:[{field:'sex',op:'eq',value:'f'},{field:'age',op:'gte',value:18}]}},disaggregate_by:['district']}},
   {indicator_id:'i2',definition:{kind:'ratio',numerator:{sum:{form:'survey',field:'income'}},denominator:{count:{form:'other',where:{field:'zone',op:'eq',value:'x'}}}}},
   {indicator_id:'i3',definition:{kind:'sum',value:{form:'other',field:'amount'}}},
  ];
  const read=rulesReading(definitions,'survey');
  expect(read.indicators).toEqual(['i1','i2']);
  expect([...read.fields].sort()).toEqual(['age','district','income','sex']);
  expect(read.entity).toBe(true);
  expect(rulesReading(definitions,'other').entity).toBe(false);
  expect(rulesReading(definitions,'none')).toEqual({indicators:[],fields:new Set(),entity:false});
 });
 it('translates the server form errors and keeps anything else',()=>{
  expect(arabicDetail("field 'q_1': label is empty")).toContain('نص السؤال فارغ');
  expect(arabicDetail("field 'sex': select_one needs at least two options")).toContain('خيارين');
  expect(arabicDetail('title is empty')).toBe('عنوان النموذج فارغ.');
  expect(arabicDetail('entity_key_field must be a text or integer field')).toContain('عدد صحيح');
  expect(arabicDetail('something else')).toBe('something else');
  // The Latin id is isolated, so it keeps its direction inside the Arabic sentence.
  expect(arabicDetail("field 'q_1': duplicate id")).toContain(String.fromCharCode(0x2068)+'q_1'+String.fromCharCode(0x2069));
 });
});

// The screen itself, rendered on the server with a stand-in for the workspace store (no DOM needed).
const store=vi.hoisted(()=>({value:{} as Record<string,unknown>}));
vi.mock('../workspace/Context',()=>({useWorkspace:()=>store.value}));
function screen(state:Record<string,unknown>,hash='#/forms'){
 Object.assign(globalThis,{window:{location:{hash}}});
 store.value={draft:{results:[],indicators:[],forms:[],definitions:[],open_questions:[]},connected:true,busy:false,error:null,run:async()=>null,refresh:async()=>{},...state};
 return renderToStaticMarkup(createElement(Forms));
}
const survey={id:'1',key:'survey',title:'مسح الأسر',status:'draft',schema:{schema_version:1,title:'مسح الأسر',entity_key_field:'hh_id',origin:'document',source:'survey.xlsx > Sheet1',fields:[
 {id:'hh_id',type:'text',label:'رمز الأسرة',required:true,options:[],unit:null,constraints:null,pii:true,qualitative:false,section:'بيانات الأسرة'},
 {id:'size',type:'integer',label:'عدد أفراد الأسرة',required:false,options:[],unit:'فرد',constraints:{min:1,max:30},pii:false,qualitative:false,section:'بيانات الأسرة'},
 {id:'water',type:'select_one',label:'مصدر المياه',required:true,options:[{value:'network',label:'الشبكة العامة'},{value:'tank',label:'صهريج'}],unit:null,constraints:null,pii:false,qualitative:false,section:'الخدمات'},
 {id:'story',type:'text',label:'صف التغيير الذي لاحظته',required:false,options:[],unit:null,constraints:null,pii:false,qualitative:true,section:null},
]}};
const published={...survey,id:'2',key:'baseline',title:'مسح خط الأساس',status:'published',schema:{...survey.schema,title:'مسح خط الأساس',origin:'ai',source:null}};
const indicators=[{id:'i1',name:'عدد الأسر المستفيدة'}],definitions=[{id:'d1',indicator_id:'i1',status:'draft',definition:{kind:'count',count:{form:'survey',unit:'entity',where:{field:'water',op:'eq',value:'network'}}}}];

describe('form builder screen',()=>{
 it('asks for the server when not connected and shows no invented forms',()=>{
  const html=screen({connected:false});
  expect(html).toContain('الخادم غير متصل');
  expect(html).not.toContain('q-builder-list');
 });
 it('explains how to get a first form',()=>{
  const html=screen({});
  expect(html).toContain('لا توجد نماذج بعد');
  expect(html).toContain('href="#/framework"');
  expect(html).toContain('نموذج جديد');
 });
 it('edits a draft form from the uploaded files with a live preview',()=>{
  const html=screen({draft:{results:[],indicators,forms:[published,survey],definitions,open_questions:[]}},'#/forms?form=survey');
  expect(html).toContain('id="builder-title"');
  expect(html).toContain('value="مسح الأسر"');
  expect(html).toContain('من ملفاتك');
  expect(html).toContain('يغذي ١ مؤشرات');
  expect(html).toContain('دون معرّف: يُحسب كل سجل');
  expect(html).toContain('تقرؤه قاعدة حساب');
  expect(html).toContain('معاينة — لا تُرسل الإجابات');
  expect(html).toContain('<h4 dir="auto">بيانات الأسرة</h4>');
  expect(html).toContain('<h4 dir="auto">الخدمات</h4>');
  expect(html).toContain('type="radio"');
  expect(html).toContain('<textarea');
  expect(html).toContain('(فرد)');
  expect(html).toContain('القيمة بين ١ و٣٠.');
  expect(html).toContain('بيانات شخصية: لا تُرسل');
  expect(html).toContain('حفظ النموذج');
  expect(html).not.toContain('ملاحظات تمنع الحفظ');
 });
 it('shows a published form read-only and suggests a new form',()=>{
  const html=screen({draft:{results:[],indicators,forms:[published,survey],definitions,open_questions:[]}},'#/forms?form=baseline');
  expect(html).toContain('هذا النموذج منشور ويجمع البيانات');
  expect(html).toContain('نسخ إلى نموذج جديد');
  expect(html).not.toContain('id="builder-title"');
  expect(html).not.toContain('حفظ النموذج');
  expect(html).toContain('معاينة — لا تُرسل الإجابات');
 });
 it('falls back to the first form when the link names no known form',()=>{
  const html=screen({draft:{results:[],indicators:[],forms:[survey,published],definitions:[],open_questions:[]}},'#/forms?form=missing');
  expect(html).toContain('value="مسح الأسر"');
  expect(html).toContain('لا يغذي مؤشرات بعد');
 });
});
