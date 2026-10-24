import {describe,it,expect} from 'vitest';
import {WorkspaceApi,normalizeBase,ApiError} from '../workspace/api';
describe('repository API contracts',()=>{
 it('uses root MVP paths and sends form data in the documented envelope',async()=>{
  let url='',init:RequestInit|undefined;
  const transport:typeof fetch=async(input,options)=>{url=String(input);init=options;return new Response(JSON.stringify({id:'test-receipt',form:'attendance',entity_key:null,collected_at:'2026-10-24T12:00:00Z',data:{count:0}}),{status:201});};
  const result=await new WorkspaceApi('http://localhost:8000/',transport).submit('attendance',{count:0});
  expect(url).toBe('http://localhost:8000/forms/attendance/submissions');
  expect(JSON.parse(String(init?.body))).toEqual({data:{count:0}});
  expect(init?.method).toBe('POST');expect(result.data.count).toBe(0);
 });
 it('uploads actual selected files and defaults extraction off',async()=>{
  let url='',sent:FormData|null=null;
  const transport:typeof fetch=async(input,options)=>{url=String(input);sent=options?.body as FormData;return new Response(JSON.stringify({id:'test-upload',status:'parsed',files:[],parsed:[],error:null}));};
  await new WorkspaceApi('http://localhost:8000',transport).upload([new File(['a,b\n1,2'],'user.csv',{type:'text/csv'})]);
  expect(url).toBe('http://localhost:8000/upload?extract=false');
  expect((sent! as FormData).getAll('files').map(file=>(file as File).name)).toEqual(['user.csv']);
 });
 it('returns server validation details instead of invented results',async()=>{
  const api=new WorkspaceApi('http://localhost:8000',async()=>new Response(JSON.stringify({error:{message:'validation failed',details:['count: required']}}),{status:422}));
  await expect(api.submit('attendance',{})).rejects.toMatchObject({message:'validation failed',details:['count: required'],status:422});
 });
 it('does not replace an unavailable backend with fabricated data',async()=>{
  const api=new WorkspaceApi('http://localhost:8000',async()=>{throw new TypeError('Network failed');});
  await expect(api.dashboard()).rejects.toBeInstanceOf(ApiError);
 });
 it('refuses non-http destinations and embedded credentials',()=>{
  expect(normalizeBase('https://example.org/')).toBe('https://example.org');
  for(const base of ['file:///tmp/app','https://name:secret@example.org','https://example.org?secret=x'])expect(()=>normalizeBase(base)).toThrow();
 });
});
