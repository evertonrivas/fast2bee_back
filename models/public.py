import jwt
import uuid
import bcrypt
from os import path,environ
from dotenv import load_dotenv
from f2bconfig import CustomerAction
from models.helpers import db as dbForModel
from sqlalchemy import ForeignKey, func, Column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime,timedelta, timezone
from sqlalchemy import DECIMAL, Date,Index, Boolean
from sqlalchemy import String, Integer, CHAR, DateTime, SmallInteger

BASEDIR = path.abspath(path.dirname(__file__))
load_dotenv(path.join(BASEDIR, '.env'))

def _save_customer_log(id:int,id_customer:str, act:CustomerAction, p_log_action:str):
    log:SysCustomerHistory = SysCustomerHistory()
    setattr(log,"id_user",id)
    setattr(log,"action",act.value)
    setattr(log,"history",p_log_action)
    setattr(log,"id_customer",id_customer)
    setattr(log,"date_created",datetime.now())
    dbForModel.session.add(log)
    dbForModel.session.commit()

class SysUsers(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id              = Column(Integer,primary_key=True,nullable=False,autoincrement=True)
    id_customer     = Column(ForeignKey(SysCustomer.id),primary_key=True,nullable=False)
    name            = Column(String(255),nullable=False,comment="Nome do usuário")
    username        = Column(String(100), nullable=False,unique=True)
    email           = Column(String(255),nullable=False,unique=True)
    password        = Column(String(255), nullable=False)
    type            = Column(CHAR(1),nullable=False,default='L',server_default='L',comment='A = Administrador, L = Lojista, I = Lojista (IA), R = Representante, V = Vendedor, C = Company User')
    date_created    = Column(DateTime,nullable=False,server_default=func.now())
    date_updated    = Column(DateTime,onupdate=func.now())
    active          = Column(Boolean,nullable=False,server_default='1',default=1)
    token           = Column(String(255),index=True,unique=True,nullable=True)
    token_expire    = Column(DateTime,nullable=True)
    is_authenticate = Column(Boolean,nullable=False,server_default='0',default=0)

    def hash_pwd(self,pwd:str):
        self.password = bcrypt.hashpw(pwd.encode(),bcrypt.gensalt()).decode()
        return self.password
    
    def check_pwd(self,pwd:str):
        return bcrypt.checkpw(pwd, self.password.encode()) # type: ignore

    def get_token(self,_profile:str,expires_in:int=int(str(environ.get("F2B_EXPIRE_SESSION")))):
        now        = datetime.now(tz=timezone.utc)
        expire_utc = now + timedelta(seconds=expires_in)

        #encode e decode por causa da diferenca de versoes do windows que pode retornar byte array ao inves de str
        self.token        = jwt.encode({"username":str(self.username),"profile":_profile, "iat": now, "exp": expire_utc},str(environ.get("F2B_TOKEN_KEY"))).encode().decode()
        self.token_expire = expire_utc
        return self.token
       
    def renew_token(self):
        now               = datetime.now(tz=timezone.utc) + timedelta(seconds=int(str(environ.get("F2B_EXPIRE_SESSION"))))
        data_token        = jwt.decode(str(self.token),str(environ.get("F2B_TOKEN_KEY")),algorithms=['HS256'])
        data_token["exp"] = now
        self.token        = jwt.encode(data_token,str(environ.get("F2B_TOKEN_KEY")))
        self.token_expire = now
        return now

    def revoke_token(self):
        self.token_expire = datetime.now() - timedelta(seconds=1)

    def logout(self):
        self.is_authenticate = False
        self.token = None

    @staticmethod
    def extract_token(token):
        try:
            data_token = jwt.decode(token, str(environ.get("F2B_TOKEN_KEY")), algorithms=['HS256'])
            return data_token
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def check_token(token):
        user = SysUsers.query.filter(SysUsers.token==token).first()
        if user is None or user.token_expire < datetime.now():
            return None
        return user
IDX_USERNAME = Index("IDX_USERNAME",SysUsers.username,unique=True)

class SysCustomer(dbForModel.Model):
    __bind_key__      = "public"
    __table_args__    = {"schema": "public"}
    id                = Column(UUID,primary_key=True,default=uuid.uuid4,index=True)
    name              = Column(String(255),nullable=False)
    taxvat            = Column(String(30),nullable=False,comment="CNPJ no Brasil")
    postal_code       = Column(String(30),nullable=False)
    churn             = Column(Boolean,nullable=False,server_default='0',default=0,comment="Indica se o cliente cancelou a assinatura") 
    chur_date         = Column(Date,nullable=True,comment="Data do cancelamento da assinatura") 
    churn_reason     = Column(String(255),nullable=True,comment="Motivo do cancelamento da assinatura")
    date_created      = Column(DateTime,nullable=False,server_default=func.now())
    date_updated      = Column(DateTime,onupdate=func.now())

class SysPlan(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id              = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    name            = Column(String(50),nullable=False)
    value           = Column(DECIMAL(10,2),nullable=False)
    adm_licenses    = Column(Integer,nullable=False,default=1,server_default='1',comment="Número de licenças de administrador")
    user_licenses   = Column(Integer,nullable=False,default=1,server_default='1',comment="Número de licenças de usuário")
    repr_licenses   = Column(Integer,nullable=False,default=1,server_default='1',comment="Número de licenças de representante. -1 = ilimitadas")
    store_licenses  = Column(Integer,nullable=False,default=1,server_default='1',comment="Número de licenças de loja. -1 = ilimitadas")
    istore_licenses = Column(Integer,nullable=False,default=1,server_default='1',comment="Número de licenças de loja (IA). -1 = ilimitadas")
    date_created    = Column(DateTime,nullable=False,server_default=func.now())
    date_updated    = Column(DateTime,onupdate=func.now())

class SysPayment(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema":"public"}
    id_customer     = Column(ForeignKey(SysCustomer.id),primary_key=True,nullable=False,index=True)
    id_plan         = Column(ForeignKey(SysPlan.id),primary_key=True,nullable=False,index=True)
    year            = Column(SmallInteger,primary_key=True,nullable=False)
    month           = Column(SmallInteger,primary_key=True,nullable=False)
    value           = Column(DECIMAL(10,2),nullable=False)
    discount        = Column(DECIMAL(10,2),nullable=False)
    starter         = Column(DECIMAL(10,2),nullable=False,server_default="0",default=0)
    date_created    = Column(DateTime,nullable=False,server_default=func.now())
    date_updated    = Column(DateTime,onupdate=func.now())

class SysCustomerPlan(dbForModel.Model):
    __bind_key__      = "public"
    __table_args__    = {"schema": "public"}
    id_customer       = Column(ForeignKey(SysCustomer.id),primary_key=True,nullable=False,index=True)
    id_plan           = Column(ForeignKey(SysPlan.id),primary_key=True,nullable=False,index=True)
    activate          = Column(Boolean,nullable=False,server_default='1',default=1,comment="Indica se o plano está ativo")
    activation_date   = Column(Date,nullable=False)
    inactivation_date = Column(Date,nullable=True)
    payment_model     = Column(CHAR(1),nullable=False,default='T',comment='M = Mensal, Y = Anual, T = Trial')
    payment_method    = Column(CHAR(1),nullable=False,default='N',comment='C = Credit Card, P = Pix, B = Boleto, N = None')
    date_created      = Column(DateTime,nullable=False,server_default=func.now())
    date_updated      = Column(DateTime,onupdate=func.now())

class SysCustomerUser(dbForModel.Model):
    __bind_key__   = "public"
    __table_args__ = {"schema": "public"}
    id_customer    = Column(ForeignKey(SysCustomer.id),primary_key=True,nullable=False,index=True)
    id_user        = Column(ForeignKey(SysUsers.id),primary_key=True,nullable=False,index=True)


class SysCountries(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id   = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    name = Column(String(100),nullable=False)

class SysStateRegions(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id         = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    id_country = Column(ForeignKey(SysCountries.id),nullable=False,index=True,comment="Id da tabela SysCountries",index=True)
    name       = Column(String(100),nullable=False)
    acronym    = Column(String(10),nullable=False)

class SysCities(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id              = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    id_state_region = Column(Integer,nullable=False,index=True,comment="Id da tabela CmmStateRegions",index=True)
    name            = Column(String(100),nullable=False)
    brazil_ibge_code= Column(String(10),nullable=True)

class SysCustomerHistory(dbForModel.Model):
    __bind_key__    = "public"
    __table_args__  = {"schema": "public"}
    id           = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    id_user      = Column(ForeignKey(SysUsers.id),nullable=False,index=True,comment="Id do usuário que realizou a ação",index=True)
    id_customer  = Column(ForeignKey(SysCustomer.id),nullable=False,index=True,comment="Id da tabela SysCustomer",index=True)
    action       = Column(CHAR(2),nullable=False,comment="SA = System Access, DR = Data Registered, DU = Data Updated, DD = Data Deleted")
    history      = Column(String(255),nullable=False,comment="Histórico da ação realizada")
    date_created = Column(DateTime,nullable=False,server_default=func.now())

class SysConfig(dbForModel.Model):
    __bind_key__        = "public"
    __table_args__      = {"schema":"public"}
    id                  = Column(Integer,primary_key=True,nullable=False,autoincrement=True,index=True)
    id_customer         = Column(ForeignKey(SysCustomer.id),nullable=False,unique=True,index=True,comment="Id da tabela SysCustomer",index=True)
    pagination_size     = Column(SmallInteger,nullable=False,default=0)
    email_brevo_api_key = Column(String(2550),nullable=True)
    email_from_name     = Column(String(200),nullable=False)
    email_from_value    = Column(String(200),nullable=False)
    flimv_model         = Column(CHAR(1),nullable=False,default='S',comment='S = Seasonal, C = Continuous')
    dashboard_config    = Column(CHAR(1),nullable=False,default='M',comment='M = Men, W = Women, H = Wheat, D = Drink, S = Shoes, P = Piston, F = PHARMA')
    ai_model            = Column(CHAR(1),nullable=False,default='G',comment='G = Gemini, C = ChatGPT, D = Deepseek, P = Perplexity')
    ai_api_key          = Column(String(255),nullable=False)
    company_custom      = Column(Boolean,nullable=False,default=False)
    company_name        = Column(String(150),nullable=False)
    company_logo        = Column(String(255),nullable=True)
    url_instagram       = Column(String(255),nullable=True)
    url_facebook        = Column(String(255),nullable=True)
    url_linkedin        = Column(String(255),nullable=True)
    max_upload_files    = Column(SmallInteger,nullable=False,default='7')
    max_upload_images   = Column(SmallInteger,nullable=False,default='4')
    use_url_images      = Column(Boolean,nullable=False,default=False)
    track_orders        = Column(Boolean,nullable=False,default=False)