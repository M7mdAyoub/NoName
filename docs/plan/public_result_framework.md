Here are real, publicly accessible Results Frameworks from the World Bank and UNDP that you can use to test your AI-powered Monitoring & Evaluation (M&E) platform.

These are actual development-programme documents, not empty templates.

## Public Results Frameworks — Direct PDFs

| Project                                    | Organization | What's inside                                                                   | Download                                                                                                                                                   |
| ------------------------------------------ | ------------ | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Kenya Industry & Entrepreneurship          | World Bank   | KPIs, annual targets, beneficiary satisfaction indicators, monitoring plan      | [PDF](https://documents.worldbank.org/curated/en/763241529292640506/pdf/FINAL-20180529-Project-Appraisal-Document-PAD-05292018.pdf?utm_source=chatgpt.com) |
| Uzbekistan Health System Improvement       | World Bank   | Indicators, baselines, targets, beneficiary surveys, collection methods         | [PDF](https://documents1.worldbank.org/curated/en/104281468127166823/pdf/566320PAD0P1131OFFICIAL0USE0ONLY191.pdf?utm_source=chatgpt.com)                   |
| Uganda Education & Health Monitoring       | World Bank   | Attendance indicators, data sources, reporting frequencies, responsibilities    | [PDF](https://documents1.worldbank.org/curated/en/099735002202225741/pdf/P17207809ce4a20f0b85c06d0b9ee36c33.pdf?utm_source=chatgpt.com)                    |
| China Country Programme 2026–2030          | UNDP         | Results and Resources Framework, outcomes, outputs, indicators, data sources    | [PDF](https://www.undp.org/sites/g/files/zskgke326/files/2025-06/2-undp-cpd-rrf-ver-20-may-2025-05-23-final-27-may-1.pdf?utm_source=chatgpt.com)           |
| Tanzania Basic Health Services             | World Bank   | Health indicators, yearly targets, verification sources                         | [PDF](https://documents1.worldbank.org/curated/en/738831468340481116/pdf/655770PAD0P1250Official0Use0Only090.pdf?utm_source=chatgpt.com)                   |
| Côte d’Ivoire Health Systems Strengthening | World Bank   | Health and nutrition indicators, survey-based measurement, quarterly monitoring | [PDF](https://documents1.worldbank.org/curated/en/681081468244805733/pdf/PAD9640PAD0P14010Box385356B00OUO090.pdf?utm_source=chatgpt.com)                   |

Best starting point: Uzbekistan's framework, beginning on PDF page 33. It explicitly identifies indicators requiring beneficiary population surveys, making it particularly useful for testing your Results Framework → KPI extraction → survey generation → indicator mapping pipeline.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://documents1.worldbank.org\&sz=32)

World Bank

+1



## Additional useful sources

[UNDP Jordan — Results and Resources Framework 2023–2027 (PDF)](https://www.undp.org/sites/g/files/zskgke326/files/2022-09/jordan_cpd_2023-2027.pdf?utm_source=chatgpt.com)

Framework starts on PDF page 10. Includes green growth, employment, financial inclusion, gender-disaggregated targets, reporting frequencies, and responsible organizations.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.undp.org\&sz=32)

UNDP



[UNDP — 2022 Results Framework with actual outcomes](https://rolhr.undp.org/annualreport/2022/results-framework.html?utm_source=chatgpt.com)

Especially valuable for testing dashboards because it includes reported results, data sources, and comparisons with targets, not just planned indicators.

## Where to find hundreds more

| Repository                                                                                                              | What you can get                                                          |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [World Bank Documents API](https://documents.worldbank.org/en/publication/documents-reports/api?utm_source=chatgpt.com) | Search and retrieve publicly disclosed project documents programmatically |
| [UNDP Transparency Portal](https://open.undp.org/?utm_source=chatgpt.com)                                               | Browse 5,000+ development projects and associated information             |
| [UNDP Arab States Programme Documents](https://www.undp.org/arab-states/legal-framework?utm_source=chatgpt.com)         | Country-level programme frameworks across the Arab region                 |

For your MVP, I would test three distinctly different inputs: Uzbekistan Health, Kenya Entrepreneurship, and UNDP Jordan.

One important design rule: not every KPI needs a newly generated survey. Some require administrative records, existing government statistics, or direct observations. Your system should identify the appropriate collection method before generating a form.

A strong demonstration would show the uploaded PDF becoming a structured Results Framework, then automatically separating survey-measurable indicators from those requiring external data or other collection methods.
