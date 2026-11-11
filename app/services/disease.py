"""Conservative Indian crop-health information. This is advisory content, not diagnosis."""
CROP_DISEASES = {
 'tomato':['Early blight','Late blight','Bacterial wilt','Tomato leaf curl virus','Fusarium wilt'],
 'rice':['Rice blast','Bacterial leaf blight','Sheath blight','Brown spot','False smut'],
 'cotton':['Cotton bacterial blight','Fusarium wilt','Alternaria leaf spot','Grey mildew'],
 'maize':['Turcicum leaf blight','Maydis leaf blight','Downy mildew','Stalk rot','Fall armyworm damage'],
 'wheat':['Yellow rust','Brown rust','Powdery mildew','Loose smut','Karnal bunt'],
 'onion':['Purple blotch','Stemphylium blight','Downy mildew','Basal rot'],
 'potato':['Late blight','Early blight','Black scurf','Bacterial wilt'],
 'chilli':['Anthracnose/fruit rot','Leaf curl virus','Phytophthora blight','Powdery mildew'],
 'groundnut':['Tikka leaf spot','Rust','Stem rot','Collar rot'],
 'soybean':['Rust','Yellow mosaic virus','Anthracnose','Charcoal rot'],
 'banana':['Panama wilt','Sigatoka leaf spot','Bacterial wilt','Bunchy top virus'],
 'mango':['Anthracnose','Powdery mildew','Stem-end rot','Dieback'],
 'turmeric':['Rhizome rot','Leaf blotch','Leaf spot'],
 'chickpea':['Fusarium wilt','Ascochyta blight','Dry root rot'],
 'mustard':['Alternaria blight','White rust',' downy mildew','Sclerotinia stem rot'],
 'tur':['Fusarium wilt','Sterility mosaic disease','Phytophthora blight']
}


def guidance(payload):
    crop=(payload.get('crop') or 'unspecified').strip()
    key=crop.lower()
    diseases=CROP_DISEASES.get(key,[])
    region=', '.join(x for x in [payload.get('district'),payload.get('state')] if x)
    symptoms=payload.get('symptoms') or 'not supplied'
    stage=payload.get('growth_stage') or 'not supplied'
    return {
      'crop':crop,'location':region or None,'growth_stage':stage,'symptoms_reported':symptoms,
      'common_diseases':diseases,
      'early_warning_signs':['New leaf spots, yellowing, mosaic patterns or unusual curling','Wilting despite adequate soil moisture','Stem or root discoloration, soft rot or unusual lesions','Rapid spread after humid, wet or cloudy weather'],
      'possible_causes':['Fungal, bacterial or viral pathogens','Insect vectors or feeding injury','Waterlogging, drought, nutrient imbalance or soil constraints that can resemble disease symptoms'],
      'weather_risk_factors':['Prolonged leaf wetness and high humidity can favour several fungal and bacterial diseases','Warm conditions can favour some vector-borne diseases and insect pests','Waterlogged soil can increase root and collar disease risk; the specific response depends on crop and pathogen'],
      'prevention':['Use locally recommended resistant or tolerant varieties and certified planting material','Scout fields regularly and remove/manage infected residues according to local extension advice','Maintain crop spacing and drainage; avoid unnecessary overhead irrigation','Rotate crops where practical and manage volunteer plants and alternate hosts'],
      'crop_management':['Record when symptoms began, affected plant parts and the percentage of plants affected','Compare affected and healthy plants and inspect leaf undersides, stems and roots where practical','Avoid moving contaminated soil, tools or planting material between fields'],
      'organic_biological_options':['Use only biological products registered for the crop and target organism, following the current product label','Conserve natural enemies; use sanitation, crop rotation and physical monitoring where appropriate','Ask a KVK or State Agricultural University about locally validated biological-control options'],
      'ipdm':['Confirm the likely cause before choosing a treatment','Combine resistant varieties, field sanitation, crop rotation, monitoring and biological controls','Use a chemical pesticide only when needed, and only if currently registered for the crop and target pest/disease; follow the approved label and local expert guidance'],
      'treatment_safety':['No pesticide dose is prescribed here. Check the current CIBRC-approved label and State Agriculture Department/KVK guidance for the exact crop, target and formulation','Wear label-required protective equipment and observe re-entry and pre-harvest intervals','Do not mix products unless the label explicitly permits it'],
      'irrigation':['Check root-zone moisture and crop stage before irrigating','Avoid prolonged waterlogging; use drainage where needed','Prefer irrigation timing and method recommended for the crop and local soil'],
      'soil_health':['Use a recent soil test for pH and nutrient decisions','Maintain organic matter with locally appropriate residues or compost','Avoid diagnosing nutrient deficiency from leaf colour alone'],
      'crop_growing_guidance':{
        'land_preparation':'Prepare a level, well-drained seedbed appropriate to the crop and soil; avoid working soil when excessively wet.',
        'suitable_soil':'Soil suitability varies by crop and cultivar; use State Agricultural University/KVK recommendations for the district.',
        'climate':'Match cultivar and sowing window to local temperature, rainfall and irrigation availability.',
        'sowing_season':'Confirm the district-specific Kharif, Rabi or Zaid window with local extension advisories.',
        'seed_selection':'Prefer certified, true-to-type seed or planting material from an authorised source.',
        'seed_treatment':'Use only crop-specific, currently approved seed treatments and follow label directions.',
        'spacing':'Use the recommended spacing for the selected variety and production system; avoid generic spacing assumptions.',
        'irrigation_schedule':'Schedule by crop stage, soil texture, rainfall and root-zone moisture; do not use a fixed calendar without local context.',
        'fertilizer_management':'Base nutrient rates on soil testing, crop requirement and local package of practices.',
        'weed_management':'Use timely intercultivation, mulching and only locally approved herbicide options where appropriate.',
        'pest_management':'Scout regularly and use integrated pest management thresholds and locally recommended controls.',
        'disease_management':'Use clean planting material, resistant varieties, rotation, sanitation and verified diagnosis.',
        'harvesting':'Harvest at crop- and market-specific maturity; avoid harvesting when produce is wet where quality may be affected.',
        'post_harvest_storage':'Dry, grade and store produce under crop-specific moisture, ventilation and pest-control recommendations.'
      },
      'when_to_contact_kvk':'Contact the nearest KVK or district agriculture officer if symptoms spread quickly, plants wilt despite adequate moisture, the stem/root is affected, the crop is at risk of major loss, or treatment choice is uncertain.',
      'image_prediction':{'status':'not_performed','message':'No image model was run by this guidance endpoint. A symptom description alone cannot confirm a disease.'},
      'guidance_type':'general_agricultural_information','verification':'General guidance only; confirm local recommendations with the district KVK/State Agricultural University.'
    }
