from google import genai
from .artificial_intelligence import ArtificialInteligence
# from google.genai import types

class Gemini(ArtificialInteligence):
    def __init__(self,_ai_key) -> None:
        super().__init__(_ai_key)
        self.ai_model = genai.Client(api_key=self.ai_api_key)
    
    def suggest_email(self, subject: str,type:str):
        if type=="M":
            question = "Melhore o texto para que tenha uma linguagem mais profissional e possa ser enviado por e-mail para cada cliente da minha lista de contatos.\n "+subject
        elif type=="A":
            question = "Crie um texto de apresentação profissional de produtos para ser enviado por e-mail à cada cliente da minha lista de contatos. O texto será baseado no que já tenho logo abaixo.\n"+subject
        elif type=="P":
            question = "Crie uma proposta de venda de produtos para ser enviada por e-mail à cada cliente da minha lista. A proposta terá como premissas: "+subject
        elif type=="O":
            question = "Crie um exemplo de orçamento para que seja enviada por e-mail à cada cliente da minha lista com base nos seguintes dados: "+subject+ " coloque os produtos em uma tabela HTML sem bordas e com cabeçalho em negrito."
        
        # content = self.ai_model.generate_content(question).text
        content = self.ai_model.models.generate_content(
            model='gemini-2.0-flash-001', contents=question
        )
        new_content = str(content).split("\n\n")
        subject = new_content[0].replace("##","").replace("Assunto: ","")
        content = "<br><br>".join(new_content[1:])
        content = content.replace("\n","")
        return {
            "subject": subject,
            "content": content
        }
    
    