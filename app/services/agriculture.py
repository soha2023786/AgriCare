from datetime import datetime
from typing import Dict

def fertilizer_recommendation(data: Dict):
    n, p, k, ph = data["nitrogen"], data["phosphorus"], data["potassium"], data["ph"]
    notes, nutrients = [], []
    for name, value in (("Nitrogen", n), ("Phosphorus", p), ("Potassium", k)):
        if value < 40:
            nutrients.append(name)
    if ph < 5.5:
        notes.append("Soil is acidic; consider a soil-test-guided liming plan.")
    elif ph > 7.5:
        notes.append("Soil is alkaline; check micronutrient availability.")
    else:
        notes.append("Measured pH is within a commonly suitable range for many crops.")
    if nutrients:
        notes.append("Low readings reported for: " + ", ".join(nutrients) + ".")
    else:
        notes.append("NPK readings are not below this app's simple screening threshold.")
    return {
        "crop": data["crop"], "soil_type": data["soil_type"],
        "assessment": "Screening estimate based on user-entered NPK and pH values.",
        "low_nutrients": nutrients,
        "recommendations": notes,
        "next_step": "Confirm with a local soil laboratory and follow crop-specific, region-specific fertilizer rates before application.",
        "disclaimer": "Not a laboratory diagnosis. No fertilizer quantity is prescribed because units, soil-test method, crop stage and local recommendations are not yet verified."
    }

def market_prices(crop, market):
    """Return only verified provider records; never manufacture mandi prices."""
    import os, json, urllib.parse, urllib.request
    api_key = os.getenv("DATA_GOV_IN_API_KEY")
    resource_id = os.getenv("AGMARKNET_RESOURCE_ID")
    if not api_key or not resource_id:
        return {"crop": crop, "market": market, "records": [], "source": None,
                "updated_at": None, "message": "This current-price endpoint has no configured live provider. Use the separate historical-market endpoint for imported FY 2025–26 records; current data is not substituted for historical observations."}
    params = urllib.parse.urlencode({"api-key": api_key, "format": "json", "limit": 100,
        "filters[commodity]": crop, "filters[market]": market})
    url = f"https://api.data.gov.in/resource/{resource_id}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgriCareAI/2.1"})
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        fields = payload.get("records", [])
        records = []
        for row in fields:
            records.append({"commodity": row.get("commodity", crop), "market": row.get("market", market),
                "arrival_date": row.get("arrival_date"), "min_price": row.get("min_price"),
                "max_price": row.get("max_price"), "modal_price": row.get("modal_price")})
        return {"crop": crop, "market": market, "records": records, "source": "data.gov.in / Agmarknet",
                "updated_at": max((r.get("arrival_date") or "" for r in records), default=None),
                "message": None if records else "The provider returned no matching records for this crop and market."}
    except Exception as exc:
        return {"crop": crop, "market": market, "records": [], "source": "data.gov.in / Agmarknet",
                "updated_at": None, "message": "The live market-data provider could not be reached. Please retry later."}

def digital_twin(data):
    moisture = data["soil_moisture"]
    temp = data["temperature_c"]
    irrigation = data["irrigation_percent"]
    days = data["days"]
    # Illustrative rule-based scenario; not a calibrated crop-growth model.
    moisture_after = max(0, min(100, moisture + (irrigation - 100) * 0.12 * days - max(0, temp - 30) * 0.25 * days))
    risk = "Low"
    if moisture_after < 20 or temp > 38:
        risk = "High"
    elif moisture_after < 30 or temp > 34:
        risk = "Moderate"
    return {
        "crop": data["crop"], "area_acres": data["area_acres"],
        "simulation_days": days, "starting_moisture_percent": moisture,
        "irrigation_setting_percent": irrigation,
        "estimated_moisture_after_simulation": round(moisture_after, 1),
        "heat_stress_indicator": "Elevated" if temp > 35 else "Not elevated",
        "scenario_risk": risk,
        "model_type": "Illustrative rule-based simulation",
        "notice": "This is a demonstration scenario, not a scientifically validated digital twin or yield forecast."
    }

def farming_assistant(question, language, context=None, history=None):
    """Use configured LLM for grounded, language-locked advice; safe fallback otherwise."""
    import os, json, urllib.request
    language = language if language in ("English", "Hindi", "Telugu") else "English"
    context = context or {}
    crops = ("rice, wheat, maize, sorghum, pearl millet, finger millet, barley, chickpea, pigeon pea, "
             "mung bean, urad, lentil, groundnut, soybean, mustard, sesame, sunflower, cotton, sugarcane, "
             "jute, tea, coffee, coconut, arecanut, rubber, banana, mango, citrus, grapes, pomegranate, "
             "papaya, guava, tomato, onion, potato, chilli, brinjal, okra, cabbage, cauliflower, turmeric, "
             "ginger, black pepper, cardamom, coriander, cumin and other regionally cultivated crops")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if api_key:
        lang_rule = {"English":"Respond only in clear English.", "Hindi":"केवल सरल और स्पष्ट हिंदी में उत्तर दें।", "Telugu":"సరళమైన తెలుగులో మాత్రమే సమాధానం ఇవ్వండి."}[language]
        system = ("You are AgriCare AI, an India-focused agricultural extension assistant. "
          "Give cautious, evidence-aware, practical guidance. Consider Indian agro-climatic regions, state, district, "
          "season, crop stage, soil and weather when provided. Crop coverage includes: " + crops + ". "
          "Ask concise follow-up questions when essential details are missing. Never invent live weather, mandi prices, "
          "pesticide registrations, model predictions, or exact fertilizer doses. Distinguish general guidance from "
          "verified local recommendations. For pesticide use, advise checking current CIBRC label and local KVK/SAU guidance. " + lang_rule)
        messages=[{"role":"system","content":system}]
        for item in (history or [])[-10:]:
            if item.get("role") in ("user","assistant") and item.get("content"):
                messages.append({"role":item["role"],"content":item["content"][:5000]})
        messages.append({"role":"user","content":json.dumps({"question":question,"farm_context":context},ensure_ascii=False)})
        payload = {"model": model, "temperature": 0.2, "messages": messages}
        try:
            req=urllib.request.Request("https://api.openai.com/v1/chat/completions",data=json.dumps(payload).encode(),
              headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=35) as response: result=json.loads(response.read().decode())
            answer=result["choices"][0]["message"]["content"].strip()
            return {"language":language,"answer":answer,"provider":"configured AI model"}
        except Exception:
            pass
    q=question.lower()
    topic="general"
    if any(x in q for x in ["soil","మట్టి","मिट्टी","ph","npk"]): topic="soil"
    elif any(x in q for x in ["water","irrigat","నీరు","నీటిపారుదల","पानी","सिंचाई"]): topic="irrigation"
    elif any(x in q for x in ["pest","insect","worm","పురుగు","कीट"]): topic="pest"
    elif any(x in q for x in ["disease","spot","yellow","wilting","వ్యాధి","మచ్చ","रोग","पीला"]): topic="disease"
    elif any(x in q for x in ["crop","grow","sow","season","పంట","విత్త","फसल","बुवाई"]): topic="crop"
    elif any(x in q for x in ["market","price","mandi","ధర","మండి","भाव","कीमत"]): topic="market"
    elif any(x in q for x in ["weather","rain","forecast","temperature","मौसम","बारिश","వాతావరణం","వర్షం"]): topic="weather"
    if topic=="general" and history:
        previous=next((x.get("content","").lower() for x in reversed(history) if x.get("role")=="user"),"")
        if any(x in previous for x in ["soil","మట్టి","मिट्टी","npk"]): topic="soil"
        elif any(x in previous for x in ["irrigat","నీటిపారుదల","सिंचाई"]): topic="irrigation"
        elif any(x in previous for x in ["pest","insect","పురుగు","कीट"]): topic="pest"
        elif any(x in previous for x in ["disease","spot","yellow","వ్యాధి","रोग"]): topic="disease"
        elif any(x in previous for x in ["crop","grow","పంట","फसल"]): topic="crop"
        elif any(x in previous for x in ["market","price","mandi","ధర","भाव"]): topic="market"
        elif any(x in previous for x in ["weather","rain","forecast","వాతావరణం","मौसम"]): topic="weather"
    fallbacks = {
      "English": {
        "general":"I can guide you on crop selection, soil health, irrigation, fertilizer planning, pests, diseases and Indian farming practices. Tell me your state/district, crop, season and crop stage so I can narrow the guidance.",
        "soil":"For soil management, use a recent soil-test report for pH, organic carbon and available N-P-K. Avoid choosing fertilizer quantities from visual symptoms alone. Share the crop, soil type, test values and district for more relevant guidance.",
        "irrigation":"Check moisture in the crop root zone and consider crop stage, soil texture and recent rainfall before irrigating. Avoid waterlogging and unnecessary irrigation. Share crop, soil type and growth stage for a more specific schedule.",
        "pest":"Inspect the underside of leaves, growing points and stems; note the pest, affected area and whether natural enemies are present. Use field sanitation, monitoring and locally recommended integrated pest management. Do not apply a pesticide until the pest is identified and the current label confirms the crop and target.",
        "disease":"A text description cannot confirm a plant disease. Note the affected plant part, symptom duration, crop stage, recent weather and how widely symptoms have spread. Compare affected and healthy plants and consult a KVK if symptoms spread quickly. Avoid pesticide treatment before confirmation.",
        "crop":"Crop choice and sowing dates depend on district, season, rainfall, irrigation and soil. Share your state/district, available water, season and land area so I can narrow suitable options.",
        "market":"I should not guess a mandi price. Open Market Intelligence and select the crop, state, district and mandi to view imported, source-attributed historical records. If no matching records are stored, the application will say so.",
        "weather":"For a live farm forecast, provide your farm latitude and longitude in the farm context fields. The app will retrieve current weather from Open-Meteo; without coordinates I will not guess local conditions."},
      "Hindi": {
        "general":"मैं फसल चयन, मिट्टी, सिंचाई, उर्वरक, कीट, रोग और भारतीय खेती के तरीकों पर मार्गदर्शन दे सकता हूँ। अधिक उपयोगी सलाह के लिए अपना राज्य/जिला, फसल, मौसम और फसल की अवस्था बताएं।",
        "soil":"मिट्टी के प्रबंधन के लिए pH, जैविक कार्बन और उपलब्ध N-P-K की हाल की मिट्टी-जांच रिपोर्ट का उपयोग करें। केवल पत्तियों के रंग के आधार पर उर्वरक की मात्रा तय न करें। फसल, मिट्टी का प्रकार, जांच के मान और जिला बताएं।",
        "irrigation":"सिंचाई से पहले जड़ क्षेत्र की नमी, फसल की अवस्था, मिट्टी और हाल की बारिश देखें। जलभराव और अनावश्यक सिंचाई से बचें। फसल, मिट्टी और अवस्था बताएं।",
        "pest":"पत्तियों के नीचे, नई बढ़वार और तनों की जांच करें। कीट, प्रभावित क्षेत्र और लाभकारी कीटों की मौजूदगी नोट करें। निगरानी, खेत की सफाई और स्थानीय IPM सलाह अपनाएं। कीट की पहचान और वर्तमान लेबल की पुष्टि के बिना कीटनाशक न डालें।",
        "disease":"केवल लिखे हुए लक्षणों से रोग की पुष्टि नहीं हो सकती। प्रभावित भाग, लक्षणों की अवधि, फसल की अवस्था, हाल का मौसम और फैलाव नोट करें। लक्षण तेजी से फैलें तो KVK से संपर्क करें। पुष्टि से पहले दवा का उपयोग न करें।",
        "crop":"फसल और बुवाई का समय जिला, मौसम, वर्षा, सिंचाई और मिट्टी पर निर्भर करता है। अपना राज्य/जिला, पानी की उपलब्धता, मौसम और क्षेत्र बताएं।",
        "market":"मैं मंडी भाव का अनुमान नहीं लगाऊँगा। Market Intelligence में फसल, राज्य, जिला और मंडी चुनकर स्रोत सहित आयात किए गए ऐतिहासिक रिकॉर्ड देखें। रिकॉर्ड न होने पर ऐप उपलब्धता बताएगा।",
        "weather":"खेत का लाइव मौसम जानने के लिए Farm context में खेत का latitude और longitude दें। ऐप Open-Meteo से मौसम प्राप्त करेगा; निर्देशांक के बिना मैं स्थानीय मौसम का अनुमान नहीं लगाऊँगा।"},
      "Telugu": {
        "general":"పంటల ఎంపిక, నేల ఆరోగ్యం, నీటిపారుదల, ఎరువులు, పురుగులు, వ్యాధులు మరియు భారతీయ వ్యవసాయ పద్ధతులపై మార్గదర్శనం ఇస్తాను. మీ రాష్ట్రం/జిల్లా, పంట, సీజన్, పంట దశ వివరాలు ఇవ్వండి.",
        "soil":"నేల నిర్వహణకు pH, సేంద్రీయ కార్బన్, అందుబాటులో ఉన్న N-P-K విలువలతో తాజా నేల పరీక్ష నివేదికను ఉపయోగించండి. ఆకుల రంగు ఆధారంగా మాత్రమే ఎరువు పరిమాణం నిర్ణయించవద్దు. పంట, నేల రకం, పరీక్ష విలువలు, జిల్లా తెలియజేయండి.",
        "irrigation":"నీరు పెట్టే ముందు వేర్ల ప్రాంతంలోని తేమ, పంట దశ, నేల స్వభావం, ఇటీవలి వర్షాన్ని పరిశీలించండి. నీరు నిల్వ ఉండకుండా, అవసరం లేని నీటిపారుదల నివారించండి. పంట, నేల రకం, దశ వివరాలు ఇవ్వండి.",
        "pest":"ఆకుల అడుగు భాగం, కొత్త చిగుళ్లు, కాండాలను పరిశీలించండి. పురుగు, ప్రభావిత ప్రాంతం, సహజ శత్రు పురుగుల ఉనికిని నమోదు చేయండి. పర్యవేక్షణ, పొలం శుభ్రత, స్థానిక IPM సూచనలు పాటించండి. పురుగు నిర్ధారణ మరియు ప్రస్తుత లేబుల్ ధృవీకరణ లేకుండా మందు వాడవద్దు.",
        "disease":"వ్రాతపూర్వక లక్షణాల ఆధారంగా మాత్రమే మొక్క వ్యాధిని నిర్ధారించలేం. ప్రభావిత భాగం, లక్షణాల వ్యవధి, పంట దశ, ఇటీవలి వాతావరణం, వ్యాప్తి వివరాలు నమోదు చేయండి. లక్షణాలు వేగంగా పెరిగితే KVKను సంప్రదించండి. నిర్ధారణకు ముందు మందు వాడవద్దు.",
        "crop":"పంట ఎంపిక, విత్తే సమయం జిల్లా, సీజన్, వర్షపాతం, నీటి లభ్యత, నేలపై ఆధారపడి ఉంటుంది. మీ రాష్ట్రం/జిల్లా, నీటి లభ్యత, సీజన్, భూమి విస్తీర్ణం చెప్పండి.",
        "market":"మండి ధరను నేను ఊహించి చెప్పను. Market Intelligenceలో పంట, రాష్ట్రం, జిల్లా, మండీ ఎంచుకుని దిగుమతి చేసిన మూలాధార చారిత్రక రికార్డులను చూడండి. రికార్డులు లేకపోతే యాప్ అందుబాటులో లేవని చూపిస్తుంది.",
        "weather":"మీ పొలానికి ప్రత్యక్ష వాతావరణం తెలుసుకోవడానికి Farm contextలో అక్షాంశం, రేఖాంశం ఇవ్వండి. యాప్ Open-Meteo నుంచి వాతావరణాన్ని పొందుతుంది; కోఆర్డినేట్లు లేకుండా స్థానిక వాతావరణాన్ని ఊహించను."}}
    return {"language":language,"answer":fallbacks[language][topic],"provider":"Farmer Assistant guided knowledge fallback","topic":topic,"needs_configuration":True}

def dashboard_summary():
    return {
        "platform": "AgriCare AI",
        "modules": ["Zone Monitoring", "Disease Detection", "Predictive Analytics", "Smart Irrigation",
                    "AI Assistant", "Fertilizer Recommendation", "Pest Detection",
                    "Market Price Intelligence", "Multilingual Voice Assistant", "Farm Digital Twin"],
        "status": "API operational",
    }

def disease_guidance(crop):
    return {"crop": crop, "guidance": "Inspect affected leaves, isolate severely affected plants where practical, avoid overhead watering when leaf disease is suspected, and seek local diagnosis. Image-based disease prediction requires your original trained model."}

def irrigation_advice(moisture):
    if moisture < 25:
        advice = "Soil moisture is low. Check root-zone moisture and crop stage; irrigation may be needed."
    elif moisture < 45:
        advice = "Soil moisture is moderate. Recheck conditions and weather before irrigating."
    else:
        advice = "Soil moisture is relatively high. Avoid unnecessary irrigation and monitor drainage."
    return {"soil_moisture_percent": moisture, "advice": advice}
