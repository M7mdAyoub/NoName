export const repository={name:'M7mdAyoub/Qiyas',url:'https://github.com/M7mdAyoub/Qiyas',commit:'b342a953a165fe1c8ba504c6cc3ff345c61c035a'};
export const sourceFile=(path:string)=>`${repository.url}/blob/${repository.commit}/${path}`;
export const documents=[
 {title:'نطاق النسخة الحالية',description:'مسار العمل الأساسي، نموذج البيانات، وحدود النسخة الأولى.',path:'docs/MVP.md',tag:'نطاق العمل'},
 {title:'سجل تنفيذ الخادم',description:'ما تم تنفيذه، طريقة التشغيل، وتفاصيل تسليم المراحل.',path:'docs/HANDOFF.md',tag:'التنفيذ'},
 {title:'خطة المنصة التفصيلية',description:'هياكل النماذج والمؤشرات والحسابات. بعض وظائفها خارج نطاق النسخة الحالية.',path:'docs/plan/BACKEND_IMPLEMENTATION_PLAN.md',tag:'مرجع تقني'},
 {title:'مصادر أطر نتائج منشورة',description:'قائمة الوثائق العامة الأصلية للبنك الدولي وبرنامج الأمم المتحدة الإنمائي.',path:'docs/plan/public_result_framework.md',tag:'المصادر'}
];
// Bibliography from the repository; these links are documents, never invented application data.
export const frameworkSources=[
 {title:'البرنامج القطري للأردن',organization:'برنامج الأمم المتحدة الإنمائي',detail:'٢٠٢٣–٢٠٢٧ · النمو الأخضر والتشغيل والشمول المالي',url:'https://www.undp.org/sites/g/files/zskgke326/files/2022-09/jordan_cpd_2023-2027.pdf'},
 {title:'الصناعة وريادة الأعمال في كينيا',organization:'البنك الدولي',detail:'المؤشرات والمستهدفات وخطة المتابعة',url:'https://documents.worldbank.org/curated/en/763241529292640506/pdf/FINAL-20180529-Project-Appraisal-Document-PAD-05292018.pdf'},
 {title:'تحسين النظام الصحي في أوزبكستان',organization:'البنك الدولي',detail:'خطوط الأساس والمستهدفات ومسوحات المستفيدين',url:'https://documents1.worldbank.org/curated/en/104281468127166823/pdf/566320PAD0P1131OFFICIAL0USE0ONLY191.pdf'},
 {title:'متابعة التعليم والصحة في أوغندا',organization:'البنك الدولي',detail:'الحضور ومصادر البيانات ودورية الإبلاغ',url:'https://documents1.worldbank.org/curated/en/099735002202225741/pdf/P17207809ce4a20f0b85c06d0b9ee36c33.pdf'},
 {title:'البرنامج القطري للصين',organization:'برنامج الأمم المتحدة الإنمائي',detail:'٢٠٢٦–٢٠٣٠ · إطار النتائج والموارد',url:'https://www.undp.org/sites/g/files/zskgke326/files/2025-06/2-undp-cpd-rrf-ver-20-may-2025-05-23-final-27-may-1.pdf'},
 {title:'الخدمات الصحية الأساسية في تنزانيا',organization:'البنك الدولي',detail:'المؤشرات الصحية والمستهدفات السنوية ومصادر التحقق',url:'https://documents1.worldbank.org/curated/en/738831468340481116/pdf/655770PAD0P1250Official0Use0Only090.pdf'},
 {title:'تعزيز النظم الصحية في كوت ديفوار',organization:'البنك الدولي',detail:'الصحة والتغذية والمسوحات والمتابعة ربع السنوية',url:'https://documents1.worldbank.org/curated/en/681081468244805733/pdf/PAD9640PAD0P14010Box385356B00OUO090.pdf'}
];
export const workflow=[
 {key:'framework',title:'ارفع إطار النتائج',description:'أضف ملف الإطار أو مجموعة الملفات المرجعية.'},
 {key:'review',title:'راجع ثم انشر',description:'تحقق من المؤشرات والنماذج وقواعد الحساب.'},
 {key:'collect',title:'اجمع البيانات',description:'استخدم النماذج المنشورة لتسجيل الإجابات.'},
 {key:'overview',title:'تابع النتائج',description:'قارن القيم المحسوبة بخط الأساس والمستهدف.'}
];
