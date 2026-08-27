# NAIP Presentation Script (Roman Urdu)

*Updated against the real, current application — every page/number below matches what's actually live on the dashboard right now, not an earlier state of the project.*

## Intro

Assalam-o-alaikum. Aaj main aapko NAIP dikhaunga — National Agriculture Intelligence Platform. Ye ek satellite-based hazard detection aur parametric insurance platform hai Pakistan ke liye. Iska north star ye hai: "nowcasting se payout tak" — matlab sirf disaster detect karna nahi, balke us detection ko seedha ek insurance decision tak le jana.

Ye project kai phases mein bana hai, aur har phase mein humne real data use kiya — koi bhi number fabricate nahi kiya. Jahan result weak nikla, wahan honestly report kiya, chupaya nahi.

## Overview Page

*[Yahan dashboard ka Overview page dikhayein]*

Ye hamara live national dashboard hai. Upar map pe Pakistan ke 126 real districts ka choropleth hai — real hazard data se banaya gaya. Neeche real-time stats ticker hai jo actual numbers dikhata hai — kitne real district-day-hazard observations hain, kitne real farm polygons hain, waghera.

Important baat: ye numbers fake nahi hain — ye seedha hamare real pipeline se aate hain, jo har 15 minute mein khud automatically chalta hai. Main aage is "live loop" ke baare mein batunga.

## Hazards Page

*[Hazards page dikhayein]*

Ye hamara core hazard detection engine hai — 11 real detectors: frost, heatwave, cold wave, hail, thunderstorm, fog, dust storm, drought, UV, cloud burst, aur heavy rain. Ye pehle se maujood system tha jo hum ne 12 pilot cities se barha kar 126 real districts tak le gaye.

Ek real bug jo mila aur theek kiya: cold-wave detector June mein galat trigger ho raha tha kyunke cloud ke upar wala temperature dekh raha tha, ground temperature nahi. Ye humne dhoonda, theek kiya, aur before/after comparison ke saath verify kiya.

Ye jo screen pe residue-burning ka number dikh raha hai — is mein do cheezein hain: ek rule-based detector, aur ek real trained AI model jo hum ne baad mein banaya. Dono saath saath chalte hain taake compare kiya ja sake.

## Water Stress Page

*[Water Stress page dikhayein]*

Yahan **teen** cheezein hain — pehle do the, teesri baad mein add hui.

Pehli: Muridke canal ka real water-stress gradient — head se tail tak, jo humne real satellite ET data se banaya, aur phir real elevation data se verify kiya ke direction sahi hai (elevation 20 meter gir rahi hai head se tail tak, r=-0.97 — ek clean, confirmed downhill trend).

Doosri: hamara flood risk model. Ye 2022 ke real Pakistan floods pe train hua — achi performance dikhayi. Lekin jab humne ise live current data pe chalaya, pata chala ke ye abhi normal monsoon aur real flood mein farq nahi kar pata — 122 mein se 126 districts flag ho rahe hain, jo ke real current flooding nahi hai. Is liye humne ise insurance trigger mein shamil **nahi** kiya — sirf yahan dashboard pe dikhaya, honestly labeled "not a flood alert."

**Teesri, real recent addition**: hamara national drought/NDVI signal. Ye project ka sab se purana, sab se pehle wala gap tha — Week 1 mein sirf 2 farm clusters, 27km ke coarse MSG grid pe. Ab hum ne ise poori tarah replace kiya — 10-meter real Sentinel-2 resolution pe, **126 mein se 126 real districts** cover karte hain. Real before/after bhi dikhaya: purana signal Layyah mein NDVI 0.07 padh raha tha (matlab near-bare-ground) — asal mein real farm polygons pe NDVI 0.495 hai, taqreeban 7 guna zyada. Matlab purana signal non-farm zameen se dominate ho raha tha, ab hum real farm-level signal dikha rahe hain. Abhi is signal se 2 districts flag ho rahe hain — Hunza aur Jafarabad.

Ye humari discipline ka ek achha example hai — jab kuch weak nikla, humne use chupaya nahi, sirf sahi jagah pe, sahi caveat ke saath dikhaya.

## Locust Page

*[Locust page dikhayein]*

Ye 3 real regions ka locust breeding-risk screen hai — real FAO satellite data aur real historical locust records se calibrate kiya gaya (49 confirmed real events pe backtest kiya, recall 24.5% tak improve kiya). Abhi teeno regions mein koi risk flag nahi ho raha — ye bhi ek real, honest result hai.

## Crop / Irrigation Page

*[Crop/Irrigation page dikhayein]*

Ye page ab **char** real trained models/results dikhata hai — pehle sirf ek tha.

**Pehla**: hamara sab se pehla trained model — irrigation classifier, 120 real farms pe. Isko bhi honestly report kiya: iski accuracy (70%) actually majority-class baseline (79.2%) se **kam** hai — humne ye chupaya nahi.

**Doosra**: hamara sab se bara model — national crop-share predictor. 2,875 real satellite-sampled points, 115 districts, real Pakistan government data (MNFSR) se label kiya gaya. Results honestly dikhaye gaye hain: wheat aur cotton mein achi performance (R² 0.58 aur 0.51), lekin sugarcane mein model fail hua (R² negative) — humne ye number chupaya nahi, seedha report kiya.

**Teesra**: genuine cross-year validation — ek real government-data-wale saal pe train karke doosre saal pe test kiya, dono directions mein. Ye Week 9 ke within-year result se zyada mushkil, zyada real test hai.

**Chautha, real naya addition**: yield prediction. Humne yahan tak koi bhi crop ka real yield (tons per hectare) predict karne ki koshish ki — same real satellite phenology features se. Yahan honestly ek **mostly negative result** mila: ek simple naive baseline ("is district ka yield is saal wohi hoga jo pichle saal tha") hamare trained model se 6 out of 8 comparisons mein behtar nikla. Wheat ka yield saal-dar-saal itna consistent hai ke satellite se usko beat karna mushkil hai. Humne ye result chupaya nahi — seedha dashboard pe likha hai.

## Exposure Risk Page

*[Exposure Risk page dikhayein]*

Ye page dikhata hai ke exposure score kaise banta hai — real government crop data, model estimates, aur jahan kuch nahi hai wahan ek fallback mask — teeno clearly labeled, kabhi mix nahi kiye jate.

**Real recent addition**: jahan model-estimate wala tier use hota hai, wahan ab ek per-crop confidence discount bhi lagta hai — jo seedha hamare trained model ke apne validated accuracy se nikala gaya hai. Matlab agar wheat ka model relatively accurate hai, to uska discount kam hai (raw score ka sirf ~2 guna chahiye trigger karne ke liye); lekin sugarcane ka model kam accurate hai, to uska discount bohot zyada hai (~8 guna raw score chahiye). Ye ek real, mathematically justified tareeqa hai different crops ki different confidence ko score mein reflect karne ka — koi arbitrary number nahi.

## Trigger Engine Page

*[Trigger Engine page dikhayein]*

Ye hamara insurance decision-engine hai. Har trigger event ka poora audit trail hai — exact hazard data, threshold, crop confidence, aur ab wo per-crop confidence multiplier bhi — sab kuch traceable. Har record pe "basis risk" ka note hai, jo saaf batata hai: ye trigger sirf ek indication hai, kisi farmer ke real loss ka proof nahi.

Payout khud stub hai — koi fake transaction nahi banate, kyunke real payment integration is project ka scope nahi tha.

## Crop Stress Screen Page — *(real naya page)*

*[Crop Stress Screen page dikhayein]*

Ye hamara sab se naya page hai, aur shayad hamari honesty discipline ka sab se acha example hai. Hum ne asal mein koshish ki thi ke Pakistan mein wheat rust jaisi real, specific bimariyon ka data doondein — jaise locust ke liye FAO ka real dataset mila tha. Humne RustTracker.org, published field surveys, sab check kiya. Lekin real, per-location, downloadable data kahin nahi mila — jo sites zinda thin, wo sirf maps/charts dikhati thin, koi real record nahi de rahi thin.

To humne apne aap ko rok liya — hum ne "disease detector" nahi banaya jab humare paas real disease-specific ground truth thi hi nahi. Iski jagah, humne honestly isko **"crop stress early-warning screen"** kaha — jo generic vegetation stress detect karta hai (same NDVI infrastructure jo Water Stress page pe hai), lekin ye kabhi nahi kehta ke "ye disease hai" ya "ye pest hai." Page ke upar hi, sab se pehle, ek clear notice hai: **"NOT A PEST OR DISEASE DIAGNOSIS."**

Do real signals hain: ek jo sustained/chronic stress dhoondta hai, aur ek jo acute/sudden decline dhoondta hai. Jo districts dono signals pe flag hote hain (19 districts), wo sab se strong real case hai. Jo sirf ek signal pe flag hote hain (89 districts), unko humne honestly ek "looser view" kaha — kyunke itne kam points ke saath ye chance se bhi ho sakta hai.

## Models-in-Production Page

*[Models-in-Production page dikhayein]*

Ye page sab real trained AI models ek jagah dikhata hai — fire classifier, crop-share model, flood model — apne real validation numbers ke saath. Har model ka comparison hai baseline se, taake pata chale AI genuinely kuch behtar kar raha hai ya nahi.

## Demo Walkthrough

*[Demo Walkthrough page dikhayein]*

Ye hamara complete end-to-end real scenario hai — ek real hazard detection se le kar ek real trigger event tak, real matched farms ke saath. Ye poora system ka live proof hai, sirf ek mockup nahi.

## Closing — Kya alag hai is project mein

Teen cheezein jo main highlight karna chahunga:

1. Har dataset verify kiya gaya, assume nahi kiya — NASA FIRMS, FAO, Pakistan government ka MNFSR data, sab real sources se. Aur jab real data nahi mila (jaise disease surveillance ke liye), humne scope honestly kam kar diya, fake nahi kiya.
2. Jahan result weak nikla, wahan waisa hi likha — irrigation classifier baseline se kam tha, sugarcane model fail hua, yield model naive baseline se haara, flood model abhi trigger-ready nahi — humne koi bhi number chupaya nahi.
3. System ab genuinely live hai — har 15 minute mein khud data khींchta hai, process karta hai, aur dashboard update karta hai — koi manual intervention nahi chahiye.

Shukriya.

## Q&A ke liye tayyari — mumkin sawal aur jawab

**"Ye 0.346 F1 score kam nahi hai?"**
Ye accuracy nahi hai — ye ek rare-event metric hai. Rule-based detector isi kaam pe sirf F1=0.004 tha — hamara model 86 guna behtar hai, chahe absolute number chota lage.

**"Flood model insurance mein kyun nahi hai?"**
Kyunke humne khud check kiya aur pata chala ke ye abhi normal monsoon aur flood mein farq nahi kar pata. Real money involve hone se pehle, hum galat trigger nahi chahte.

**"Yield prediction model se naive baseline behtar kyun hai?"**
Kyunke wheat ka district-level yield saal-dar-saal bohot consistent hota hai — is real data mein naive baseline ka R² ~0.77 hai, jo ek bohot high bar hai. Satellite se ek **different** saal predict karna is consistency ko beat karna mushkil hai. Ye ek real, honest negative result hai, hamari koshish ki kami nahi.

**"Disease detection kyun nahi bana, jab ye scope mein tha?"**
Kyunke humne real data dhoonda aur nahi mila — jo bhi Pakistan wheat-rust surveillance sites zinda thin, wo sirf maps dikhati thin, koi downloadable per-location record nahi. Humne fake data pe model banane se inkar kiya, aur iski jagah ek honestly-scoped "crop stress screen" banaya jo kabhi diagnosis claim nahi karta.

**"Kya ye production-ready hai?"**
Nahi, aur hum ye clearly kehte hain — ye ek real, validated research platform hai jo live chal raha hai, lekin kuch cheezein (real farmer data, real SMS credentials, actuarial calibration) abhi bhi real-world partnership ki zaroorat rakhti hain.
