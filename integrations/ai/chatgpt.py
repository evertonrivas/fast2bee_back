from .artificial_intelligence import ArtificialInteligence


class ChatGPT(ArtificialInteligence):
    def __init__(self,_ai_key) -> None:
        super().__init__(_ai_key)
        pass

    def suggest_email(self, subject: str,type:str):
        pass