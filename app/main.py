from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional, Literal
import io, csv
from datetime import date
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import os
from .services import agriculture, analytics, disease, auth

BASE = Path(__file__).resolve().parent

app = FastAPI(title="AgriCare AI", version="3.0.0",
              description="Smart farming assistant with modular agriculture tools")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.exception_handler(RuntimeError)
async def runtime_configuration_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": str(exc)})

class AuthInput(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)

class RegisterInput(AuthInput):
    name: str = Field(min_length=1, max_length=120)

@app.on_event("startup")
def startup():
    # Do not let absent/unreachable production storage crash FastAPI import/startup.
    # DB-backed routes fail closed with HTTP 503; the public UI and health diagnostics remain available.
    try:
        analytics.init_db(); auth.init_auth()
    except Exception as exc:
        import logging
        logging.getLogger('agricare').error('Database initialization unavailable: %s', exc)

def require_farmer(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to access your private farm records.")
    user = auth.verify_token(authorization.split(" ",1)[1].strip())
    if not user:
        raise HTTPException(401, "Your session is invalid or expired. Please sign in again.")
    return user

@app.post("/api/auth/register")
def register_farmer(data: RegisterInput):
    if not os.getenv("AGRICARE_AUTH_SECRET"):
        raise HTTPException(503,"Set AGRICARE_AUTH_SECRET before enabling farmer accounts.")
    try:
        user=auth.register(data.name,data.email,data.password)
        token=auth.issue_token(user)
        return {"access_token":token,"token_type":"bearer","farmer":{"name":user["name"],"email":user["email"]}}
    except ValueError as exc: raise HTTPException(400,str(exc))
    except RuntimeError as exc: raise HTTPException(503,str(exc))

@app.post("/api/auth/login")
def login_farmer(data: AuthInput):
    if not os.getenv("AGRICARE_AUTH_SECRET"):
        raise HTTPException(503,"Set AGRICARE_AUTH_SECRET before enabling farmer accounts.")
    user=auth.login(data.email,data.password)
    if not user: raise HTTPException(401,"Email or password is incorrect.")
    try:return {"access_token":auth.issue_token(user),"token_type":"bearer","farmer":{"name":user.get("name",""),"email":user["email"]}}
    except RuntimeError as exc: raise HTTPException(503,str(exc))

@app.get("/api/auth/me")
def current_farmer(user=Depends(require_farmer)):
    return {"name":user.get("name",""),"email":user["email"]}

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

class FertilizerInput(BaseModel):
    crop: str
    nitrogen: float = Field(ge=0, le=500)
    phosphorus: float = Field(ge=0, le=500)
    potassium: float = Field(ge=0, le=500)
    ph: float = Field(ge=0, le=14)
    soil_type: str = "Loamy"

class TwinInput(BaseModel):
    crop: str = "Tomato"
    area_acres: float = Field(default=1, gt=0, le=10000)
    soil_moisture: float = Field(default=35, ge=0, le=100)
    temperature_c: float = Field(default=30, ge=-10, le=60)
    irrigation_percent: float = Field(default=100, ge=0, le=200)
    days: int = Field(default=7, ge=1, le=90)

class AssistantInput(BaseModel):
    question: str
    language: Literal["English", "Hindi", "Telugu"] = "English"
    context: dict = Field(default_factory=dict)
    conversation_id: str = Field(default="default", min_length=1, max_length=100)

class FarmCropInput(BaseModel):
    crop: str = Field(min_length=1, max_length=100)
    area_acres: float = Field(gt=0, le=100000)
    season: Literal["Kharif", "Rabi", "Zaid"]
    sowing_date: Optional[date] = None
    harvest_date: Optional[date] = None
    production_kg: Optional[float] = Field(default=None, ge=0)
    selling_price_inr_per_quintal: Optional[float] = Field(default=None, ge=0)
    price_verified: bool = False
    price_source: str = Field(default="", max_length=250)
    state: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    soil_type: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=1000)

class DiseaseInput(BaseModel):
    crop: str = Field(min_length=1, max_length=100)
    state: str = ""
    district: str = ""
    growth_stage: str = ""
    plant_age: str = ""
    soil_type: str = ""
    weather_conditions: str = ""
    symptoms: str = ""
    affected_parts: str = ""
    symptom_duration: str = ""



class FarmTransactionInput(BaseModel):
    transaction_type: str = Field(pattern="^(revenue|expense)$")
    crop: str = Field(min_length=1, max_length=100)
    category: str = Field(default="", max_length=100)
    amount_inr: float = Field(ge=0, le=100000000000)
    quantity_quintals: Optional[float] = Field(default=None, ge=0)
    season: str = Field(default="", max_length=50)
    state: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    transaction_date: date
    notes: str = Field(default="", max_length=1000)

@app.get("/api/health")
def health():
    try:
        analytics.check_database()
        return {"status": "ok", "application": "AgriCare AI", "version": "3.0.0", "database": analytics.database_backend()}
    except Exception as exc:
        return {"status": "degraded", "application": "AgriCare AI", "version": "3.0.0", "database": analytics.database_backend(), "database_error": str(exc), "action": "Configure a persistent DATABASE_URL and redeploy. Farmer data operations remain unavailable until storage is ready."}

@app.post("/api/fertilizer/recommend")
def fertilizer(data: FertilizerInput):
    return agriculture.fertilizer_recommendation(data.model_dump())

@app.post("/api/pest/detect")
async def pest_detect(image: UploadFile = File(...)):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed: raise HTTPException(400, "Upload a JPG, PNG or WEBP image.")
    raw=await image.read()
    if len(raw)>5*1024*1024: raise HTTPException(413,"Image must be smaller than 5 MB.")
    api_key=os.getenv("PLANTNET_API_KEY")
    if not api_key: raise HTTPException(503,"Crop image analysis is unavailable because PLANTNET_API_KEY is not configured. Use the symptom-based Disease Guidance form meanwhile.")
    try:
        import requests
        files=[("images",(image.filename or "crop.jpg",io.BytesIO(raw),image.content_type))]
        ident=requests.post("https://my-api.plantnet.org/v2/identify/all",params={"api-key":api_key,"lang":"en","no-reject":"true"},files=files,data={"organs":"leaf"},timeout=35)
        ident.raise_for_status(); ident_data=ident.json()
        plant_results=ident_data.get("results",[])
        if not plant_results: return {"status":"uncertain","plant":None,"diseases":[],"message":"The image service could not confidently identify a plant. Try a clear close-up or provide symptoms."}
        plant=plant_results[0].get("species",{}); plant_name=(plant.get("commonNames") or [plant.get("scientificNameWithoutAuthor","Unknown plant")])[0]
        disease_files=[("images",(image.filename or "crop.jpg",io.BytesIO(raw),image.content_type))]
        dr=requests.post("https://my-api.plantnet.org/v2/diseases/identify",params={"api-key":api_key,"lang":"en","no-reject":"true"},files=disease_files,data={"organs":"auto"},timeout=35)
        dr.raise_for_status(); disease_data=dr.json()
        results=[{"name":(x.get("species",{}).get("commonNames") or [x.get("species",{}).get("scientificNameWithoutAuthor","Unknown")])[0],"confidence_percent":round(float(x.get("score",0))*100,1)} for x in disease_data.get("results",[])[:3]]
        return {"status":"prediction","plant":plant_name,"plant_confidence_percent":round(float(plant_results[0].get("score",0))*100,1),"diseases":results,"source":"PlantNet API","notice":"Model predictions are screening results, not a confirmed diagnosis. Confirm with a KVK or plant pathologist before treatment. No pesticide dosage is prescribed."}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(502,"The crop image service could not complete the analysis. Please retry later or use symptom-based guidance.")

@app.get("/api/market/prices")
def market_prices(crop: str = "Tomato", market: str = "Hyderabad"):
    return agriculture.market_prices(crop, market)

@app.post("/api/digital-twin/simulate")
def digital_twin(data: TwinInput):
    return agriculture.digital_twin(data.model_dump())

@app.post("/api/assistant")
def assistant(data: AssistantInput, authorization: Optional[str] = Header(default=None)):
    if not data.question.strip(): raise HTTPException(400,"Please enter a question.")
    owner="guest"
    if authorization and authorization.lower().startswith("bearer "):
        user=auth.verify_token(authorization.split(" ",1)[1].strip())
        if user: owner=user["farmer_id"]
    history=analytics.get_assistant_history(owner,data.conversation_id,12)
    # Route relevant questions to the same verified AgriCare services used by the dashboard.
    context=dict(data.context or {})
    q=data.question.lower()
    if any(k in q for k in ["price","mandi","market","भाव","ధర","మండి","कीमत"]):
        crop_names=["Tomato","Rice","Cotton","Onion","Maize","Wheat","Groundnut","Chilli","Turmeric","Potato","Banana","Mango","Soybean","Mustard","Chickpea","Tur"]
        chosen=next((c for c in crop_names if c.lower() in q),context.get("crop"))
        if chosen:
            try: context["verified_historical_market_data"]=analytics.query_mandi("2025-04-01","2026-03-31",chosen,context.get("state"),context.get("district"),context.get("market"),"daily",1,10)
            except Exception: context["verified_historical_market_data"]={"total_records":0,"records":[]}
        else: context["verified_historical_market_data"]={"total_records":0,"records":[],"message":"Crop name not specified."}
    if any(k in q for k in ["weather","rain","forecast","मौसम","వాతావరణం","వర్షం"]):
        if context.get("latitude") is not None and context.get("longitude") is not None:
            try: context["verified_weather_context"]=analytics.weather_current(float(context["latitude"]),float(context["longitude"]))
            except Exception: context["verified_weather_context"]={"status":"unavailable","message":"Weather provider did not return data."}
        else: context["verified_weather_context"]={"status":"location_required","message":"Farm latitude and longitude are required for live weather."}
    if any(k in q for k in ["disease","spot","yellow","wilting","रोग","बीमारी","వ్యాధి","మచ్చ"]):
        context["disease_guidance_context"]=disease.guidance({"crop":context.get("crop") or next((c for c in ["Tomato","Rice","Cotton","Onion","Maize","Wheat","Groundnut","Chilli","Potato","Banana","Mango"] if c.lower() in q),"unspecified"),"state":context.get("state",""),"district":context.get("district",""),"symptoms":data.question,"growth_stage":context.get("growth_stage","")})
    if any(k in q for k in ["expense","profit","income","ఖర్చు","లాభం","खर्च","मुनाफा"]):
        if owner!="guest": context["authorised_farm_financial_summary"]=analytics.overview(crop=context.get("crop"),state=context.get("state"),district=context.get("district"),owner_id=owner)
        else: context["authorised_farm_financial_summary"]={"status":"sign_in_required"}
    result=agriculture.farming_assistant(data.question,data.language,context,history)
    def inr_indian(value):
        try: raw=str(int(round(float(value))))
        except Exception: return "₹0"
        if len(raw)<=3:return "₹"+raw
        last=raw[-3:]; head=raw[:-3]; groups=[]
        while head:
            groups.insert(0,head[-2:]); head=head[:-2]
        return "₹"+",".join(groups+[last])
    weather_data=context.get("verified_weather_context")
    if isinstance(weather_data,dict) and weather_data.get("current"):
        w=weather_data["current"]
        if data.language=="Hindi": result["answer"]=f"आपके दिए गए खेत के निर्देशांकों के अनुसार मौसम ({weather_data.get('updated_at')}): तापमान {w.get('temperature_c')}°C, आर्द्रता {w.get('humidity_percent')}%, वर्षा {w.get('precipitation_mm')} mm, हवा {w.get('wind_speed_kmh')} km/h। स्रोत: Open-Meteo। सलाह सामान्य है; सिंचाई से पहले खेत की नमी और फसल अवस्था जांचें।"
        elif data.language=="Telugu": result["answer"]=f"మీరు ఇచ్చిన పొలం కోఆర్డినేట్ల వాతావరణం ({weather_data.get('updated_at')}): ఉష్ణోగ్రత {w.get('temperature_c')}°C, తేమ {w.get('humidity_percent')}%, వర్షపాతం {w.get('precipitation_mm')} mm, గాలి వేగం {w.get('wind_speed_kmh')} km/h. మూలం: Open-Meteo. నీరు పెట్టే ముందు నేల తేమ, పంట దశ పరిశీలించండి."
        else: result["answer"]=f"Weather for the farm coordinates you supplied ({weather_data.get('updated_at')}): temperature {w.get('temperature_c')}°C, humidity {w.get('humidity_percent')}%, precipitation {w.get('precipitation_mm')} mm, wind {w.get('wind_speed_kmh')} km/h. Source: Open-Meteo. Check field moisture and crop stage before irrigation."
    elif isinstance(weather_data,dict) and weather_data.get("status")=="location_required":
        result["answer"]={"English":"Please enter your farm latitude and longitude to retrieve live weather. I will not infer the farm's exact weather from the city alone.","Hindi":"लाइव मौसम पाने के लिए कृपया खेत का latitude और longitude दर्ज करें। केवल शहर के नाम से खेत का मौसम अनुमानित नहीं करूँगा।","Telugu":"ప్రత్యక్ష వాతావరణం పొందడానికి మీ పొలం అక్షాంశం, రేఖాంశం నమోదు చేయండి. నగరం పేరుతో మాత్రమే పొలం వాతావరణాన్ని ఊహించను."}[data.language]
    financial=context.get("authorised_farm_financial_summary")
    if isinstance(financial,dict) and "total_revenue_inr" in financial and any(k in q for k in ["expense","profit","income","ఖర్చు","లాభం","खर्च","मुनाफा"]):
        rev=inr_indian(financial["total_revenue_inr"]); exp=inr_indian(financial["total_expenses_inr"]); profit=inr_indian(financial["net_profit_inr"])
        result["answer"]={"English":f"Your recorded farm transactions show revenue {rev}, expenses {exp}, and net profit/loss {profit}. These totals use only the records in your signed-in account.","Hindi":f"आपके खाते के दर्ज कृषि लेन-देन के अनुसार आय {rev}, खर्च {exp}, और शुद्ध लाभ/हानि {profit} है। ये कुल केवल आपके साइन-इन खाते के रिकॉर्ड पर आधारित हैं।","Telugu":f"మీ ఖాతాలో నమోదు చేసిన వ్యవసాయ లావాదేవీల ప్రకారం ఆదాయం {rev}, ఖర్చులు {exp}, నికర లాభం/నష్టం {profit}. ఈ మొత్తాలు మీ సైన్-ఇన్ ఖాతా రికార్డుల ఆధారంగా మాత్రమే లెక్కించబడ్డాయి."}[data.language]
    elif isinstance(financial,dict) and financial.get("status")=="sign_in_required":
        result["answer"]={"English":"Please sign in to Analytics before asking me to summarise your private farm income and expenses.","Hindi":"अपने निजी कृषि आय और खर्च का सारांश देखने के लिए पहले Analytics में साइन इन करें।","Telugu":"మీ వ్యక్తిగత వ్యవసాయ ఆదాయం, ఖర్చుల వివరాల కోసం ముందుగా Analyticsలో సైన్ ఇన్ చేయండి."}[data.language]
    market_data=context.get("verified_historical_market_data")
    if market_data is not None:
        rows=market_data.get("records",[])
        if rows:
            r=rows[0]; price=r.get("modal_price")
            if data.language=="Hindi": result["answer"]=f"FY 2025–26 के ऐतिहासिक थोक मंडी रिकॉर्ड में {r.get('commodity')} के लिए {r.get('market')}, {r.get('district')}, {r.get('state')} में {r.get('report_date')} को दर्ज मॉडल भाव ₹{price}/क्विंटल था। यह ऐतिहासिक रिकॉर्ड है, आज का लाइव भाव नहीं।"
            elif data.language=="Telugu": result["answer"]=f"FY 2025–26 చారిత్రక హోల్‌సేల్ మండీ రికార్డులో {r.get('commodity')}కు {r.get('market')}, {r.get('district')}, {r.get('state')}లో {r.get('report_date')}న నమోదు చేసిన మోడల్ ధర ₹{price}/క్వింటాల్. ఇది చారిత్రక రికార్డు మాత్రమే; నేటి ప్రత్యక్ష ధర కాదు."
            else: result["answer"]=f"In the FY 2025–26 historical wholesale mandi records, {r.get('commodity')} at {r.get('market')}, {r.get('district')}, {r.get('state')} had a reported modal price of ₹{price}/quintal on {r.get('report_date')}. This is historical, not today's live price."
        elif any(k in q for k in ["price","mandi","market","भाव","ధర","मंडी"]):
            result["answer"]={"English":"No matching historical mandi record is currently imported for that crop and location. Try another state/district or open Market Intelligence. I will not estimate a missing price.","Hindi":"इस फसल और स्थान के लिए अभी कोई मेल खाता ऐतिहासिक मंडी रिकॉर्ड आयात नहीं है। दूसरा राज्य/जिला चुनें या Market Intelligence खोलें। मैं अनुपलब्ध भाव का अनुमान नहीं लगाऊँगा।","Telugu":"ఈ పంట మరియు ప్రాంతానికి సరిపడే చారిత్రక మండీ రికార్డు ప్రస్తుతం దిగుమతి కాలేదు. మరో రాష్ట్రం/జిల్లా ఎంచుకోండి లేదా Market Intelligence తెరవండి. లేని ధరను ఊహించి చెప్పను."}[data.language]
    analytics.save_assistant_message(owner,data.conversation_id,data.language,"user",data.question)
    analytics.save_assistant_message(owner,data.conversation_id,data.language,"assistant",result.get("answer",""))
    result["conversation_id"]=data.conversation_id
    result["history_length"]=len(history)+2
    return result

# Existing-project-style sections are retained as dashboard entry points.
@app.get("/api/dashboard")
def dashboard():
    return agriculture.dashboard_summary()

@app.get("/api/disease/info")
def disease_info(crop: str = "Tomato"):
    return agriculture.disease_guidance(crop)

@app.get("/api/irrigation/advice")
def irrigation_advice(moisture: float = 35):
    if not 0 <= moisture <= 100:
        raise HTTPException(400, "Moisture must be between 0 and 100.")
    return agriculture.irrigation_advice(moisture)


@app.post("/api/analytics/transactions")
def create_analytics_transaction(data: FarmTransactionInput, user=Depends(require_farmer)):
    return analytics.add_transaction(data.model_dump(),user["farmer_id"])

@app.get("/api/analytics/transactions")
def get_analytics_transactions(start_date: Optional[str] = None,end_date: Optional[str] = None,crop: Optional[str] = None,state: Optional[str] = None,district: Optional[str] = None,season: Optional[str] = None,user=Depends(require_farmer)):
    return {"records":analytics.list_transactions(start_date,end_date,crop,state,district,user["farmer_id"],season)}

@app.put("/api/analytics/transactions/{record_id}")
def put_analytics_transaction(record_id:int,data:FarmTransactionInput,user=Depends(require_farmer)):
    result=analytics.update_transaction(record_id,data.model_dump(),user["farmer_id"])
    if not result: raise HTTPException(404,"Farm transaction not found.")
    return result

@app.delete("/api/analytics/transactions/{record_id}")
def remove_analytics_transaction(record_id:int,user=Depends(require_farmer)):
    if not analytics.delete_transaction(record_id,user["farmer_id"]): raise HTTPException(404,"Farm transaction not found.")
    return {"deleted":True,"id":record_id}

@app.get("/api/analytics/overview")
def analytics_overview(start_date: Optional[str] = None,end_date: Optional[str] = None,crop: Optional[str] = None,state: Optional[str] = None,district: Optional[str] = None,season: Optional[str] = None,user=Depends(require_farmer)):
    return analytics.overview(start_date,end_date,crop,state,district,user["farmer_id"],season)

@app.get("/api/analytics/crops")
def get_farm_crops(crop:Optional[str]=None,season:Optional[str]=None,state:Optional[str]=None,district:Optional[str]=None,start_date:Optional[str]=None,end_date:Optional[str]=None,user=Depends(require_farmer)):
    return {"records":analytics.list_crops(user["farmer_id"],crop,season,state,district,start_date,end_date)}

@app.post("/api/analytics/crops")
def create_farm_crop(data:FarmCropInput,user=Depends(require_farmer)):
    if data.sowing_date and data.harvest_date and data.sowing_date>data.harvest_date: raise HTTPException(400,"Sowing date must be on or before harvest date.")
    if data.price_verified and (not data.selling_price_inr_per_quintal or not data.price_source.strip()):
        raise HTTPException(400,"A verified price requires a positive selling price and a source/transaction reference.")
    return analytics.add_crop(data.model_dump(),user["farmer_id"])

@app.put("/api/analytics/crops/{record_id}")
def put_farm_crop(record_id:int,data:FarmCropInput,user=Depends(require_farmer)):
    if data.sowing_date and data.harvest_date and data.sowing_date>data.harvest_date: raise HTTPException(400,"Sowing date must be on or before harvest date.")
    if data.price_verified and (not data.selling_price_inr_per_quintal or not data.price_source.strip()):
        raise HTTPException(400,"A verified price requires a positive selling price and a source/transaction reference.")
    result=analytics.update_crop(record_id,data.model_dump(),user["farmer_id"])
    if not result: raise HTTPException(404,"Crop record not found.")
    return result

@app.delete("/api/analytics/crops/{record_id}")
def remove_farm_crop(record_id:int,user=Depends(require_farmer)):
    if not analytics.delete_crop(record_id,user["farmer_id"]): raise HTTPException(404,"Crop record not found.")
    return {"deleted":True,"id":record_id}

@app.get("/api/analytics/crop-performance")
def analytics_crop_performance(start_date:Optional[str]=None,end_date:Optional[str]=None,crop:Optional[str]=None,season:Optional[str]=None,state:Optional[str]=None,district:Optional[str]=None,user=Depends(require_farmer)):
    return {"records":analytics.list_crops(user["farmer_id"],crop,season,state,district,start_date,end_date)}

@app.get("/api/analytics/revenue-estimate")
def analytics_revenue_estimate(crop:str,quantity_quintals:float=Query(...,gt=0),market:str=""):
    result=agriculture.market_prices(crop,market or "")
    usable=[r for r in result.get("records",[]) if r.get("modal_price") not in (None,"")]
    if not usable:return {"status":"unavailable","crop":crop,"quantity_quintals":quantity_quintals,"currency":"INR","message":result.get("message") or "No verified modal market price is available."}
    chosen=sorted(usable,key=lambda r:r.get("arrival_date") or "",reverse=True)[0]; modal=float(chosen["modal_price"])
    return {"status":"estimated","crop":crop,"market":chosen.get("market"),"quantity_quintals":quantity_quintals,"modal_price_inr_per_quintal":modal,"estimated_gross_revenue_inr":round(quantity_quintals*modal,2),"source":result.get("source"),"price_date":chosen.get("arrival_date"),"disclaimer":"Indicative estimate only; not recorded actual income."}

@app.get("/api/market/historical/filters")
def historical_market_filters(granularity:Literal["daily","monthly"]="daily"):
    return analytics.mandi_filters(granularity)

@app.get("/api/market/historical")
def historical_market_prices(start_date:str="2025-04-01",end_date:str="2026-03-31",commodity:Optional[str]=None,state:Optional[str]=None,district:Optional[str]=None,market:Optional[str]=None,granularity:Literal["daily","monthly"]="daily",page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=500),search:Optional[str]=None):
    try: start=date.fromisoformat(start_date); end=date.fromisoformat(end_date)
    except ValueError: raise HTTPException(400,"Dates must use YYYY-MM-DD format.")
    if start>end: raise HTTPException(400,"Start date must be before end date.")
    return analytics.query_mandi(start_date,end_date,commodity,state,district,market,granularity,page,page_size,search)

@app.get("/api/market/historical/export")
def export_historical_market_prices(start_date:str="2025-04-01",end_date:str="2026-03-31",commodity:Optional[str]=None,state:Optional[str]=None,district:Optional[str]=None,market:Optional[str]=None,granularity:Literal["daily","monthly"]="daily",search:Optional[str]=None):
    try: start=date.fromisoformat(start_date); end=date.fromisoformat(end_date)
    except ValueError: raise HTTPException(400,"Dates must use YYYY-MM-DD format.")
    if start>end: raise HTTPException(400,"Start date must be before end date.")
    csv_text=analytics.export_mandi_csv({'start_date':start_date,'end_date':end_date,'commodity':commodity,'state':state,'district':district,'market':market,'granularity':granularity,'search':search})
    return StreamingResponse(io.BytesIO(csv_text.encode('utf-8-sig')),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="agricare-mandi-history-fy2025-26.csv"'})

@app.post("/api/disease/guidance")
def disease_guidance(data:DiseaseInput):
    return disease.guidance(data.model_dump())

@app.get("/api/weather/current")
def weather_current(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    try:
        return analytics.weather_current(latitude, longitude)
    except Exception:
        raise HTTPException(502, "Live weather provider is unavailable. Please retry later.")

@app.get("/api/weather/forecast")
def weather_forecast(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    try:
        data=analytics.weather_current(latitude,longitude)
        return {"source":data["source"],"updated_at":data["updated_at"],"forecast":data["forecast"]}
    except Exception:
        raise HTTPException(502, "Live weather forecast is unavailable. Please retry later.")
