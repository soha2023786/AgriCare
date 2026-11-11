import os
import unittest
from app.services import agriculture, disease

class AssistantAndDiseaseTests(unittest.TestCase):
    def test_language_locked_guided_fallbacks(self):
        old=os.environ.pop('OPENAI_API_KEY',None)
        try:
            for language, marker in [('English','soil management'),('Hindi','मिट्टी'),('Telugu','నేల')]:
                result=agriculture.farming_assistant('Help me manage soil health',language,{},[])
                self.assertEqual(result['language'],language)
                self.assertIn(marker,result['answer'])
        finally:
            if old is not None: os.environ['OPENAI_API_KEY']=old

    def test_disease_guidance_is_structured_and_non_prescriptive(self):
        result=disease.guidance({'crop':'Tomato','state':'Telangana','district':'Warangal','symptoms':'leaf spots','growth_stage':'flowering'})
        self.assertIn('Early blight',result['common_diseases'])
        self.assertIn('treatment_safety',result)
        self.assertIn('No pesticide dose is prescribed',result['treatment_safety'][0])
        self.assertEqual(result['guidance_type'],'general_agricultural_information')

if __name__=='__main__': unittest.main()
