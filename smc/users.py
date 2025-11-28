import requests
from auth import auth
from os import environ
from flask import request
from http import HTTPStatus
from datetime import datetime
from models.helpers import _get_params, db
from flask_restx import Resource ,Namespace, fields
from f2bconfig import CustomerAction, DashboardImage, DashboardImageColor, LegalEntityContactType, MailTemplates, UserType
from common import _send_email, _get_dashboard_config
from models.public import _save_customer_log, SysConfig
from models.public import SysUsers, SysCustomer, SysCustomerUser, SysPlan, SysCustomerPlan
from models.tenant import CmmLegalEntities, CmmLegalEntityContact
from sqlalchemy import Delete, Select, desc, exc, and_, asc, func, or_

ns_user = Namespace("users",description="Operações para manipular dados de usuários do sistema")

#API Models
usr_pag_model = ns_user.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Boolean
    }
)
usr_model = ns_user.model(
    "User",{
        "id": fields.Integer,
        "username": fields.String,
        "name":fields.String,
        "email": fields.String,
        "password": fields.String,
        "type": fields.String(enum=['A','L','R','V','U']),
        "date_created": fields.DateTime,
        "date_updated": fields.DateTime
    }
)

usr_return = ns_user.model(
    "UserReturn",{
        "pagination": fields.Nested(usr_pag_model),
        "data": fields.List(fields.Nested(usr_model))
    }
)

m_new_users = ns_user.model(
    "NewCustomer",{
        "id_customer": fields.Integer,
        "users": fields.List(fields.Nested(usr_model))
    }
)

@ns_user.route("/")
class UsersList(Resource):
    @ns_user.response(HTTPStatus.OK,"Obtem a listagem de usuários",usr_return)
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha oa listar registros!")
    @ns_user.param("page","Número da página de registros","query",type=int,required=True)
    @ns_user.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_user.param("query","Texto para busca","query")
    @auth.login_required
    def get(self):
        pag_num   = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size  = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query     = "" if request.args.get("query") is None else request.args.get("query")

        try:
            params    = _get_params(query)
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc
            order_by  = 'id' if not hasattr(params,'order_by') else params.order_by if params is not None else 'id'
            search    = None if not hasattr(params,"search") else params.search if params is not None else None
            list_all  = False if not hasattr(params,'list_all') else True
            filter_type   = None if not hasattr(params,'type') else params.type if params is not None else None

            if hasattr(params,'active') and params is not None:
                trash = not params.active
            else:
                trash = True

            rquery = Select(
                SysUsers.id,
                SysUsers.name,
                SysUsers.username,
                SysUsers.email,
                SysUsers.type,
                SysUsers.date_created,
                SysUsers.date_updated,
                SysUsers.active)\
                    .where(SysUsers.active==trash)\
                    .order_by(direction(getattr(SysUsers, order_by)))

            if filter_type is not None:
                rquery = rquery.where(SysUsers.type==filter_type)

            if search is not None:
                rquery = rquery.where(SysUsers.username.like("%{}%".format(search)))

            if not list_all:
                pag = db.paginate(rquery,page=pag_num,per_page=pag_size)
                rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)
                return {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next
                    },
                    "data":[{
                        "id": m.id,
                        "name": m.name,
                        "username": m.username,
                        "email": m.email,
                        "type": m.type,
                        "active": m.active,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
            else:
                return [{
                    "id": m.id,
                    "name": m.name,
                    "username": m.username,
                    "email": m.email,
                    "type": m.type,
                    "active": m.active,
                    "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                }for m in db.session.execute(rquery)]
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_user.response(HTTPStatus.OK,"Cria um ou mais novo(s) usuário(s) no sistema")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao criar!")
    @ns_user.doc(body=m_new_users,description="Dados para cadastro de novo usuário")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()

            for usr in req["users"]:

                # primeiramente busca o numero de licensas do plano assinado pelo cliente
                plan = db.session.execute(
                    Select(SysPlan.adm_licenses,
                           SysPlan.user_licenses,
                           SysPlan.store_licenses,
                           SysPlan.istore_licenses,
                           SysPlan.repr_licenses
                        ).where(
                        SysPlan.id==(Select(SysCustomerPlan.id_plan).where(SysCustomerPlan.id_customer==request.headers.get('x-customer')))
                    )
                ).first()

                total = db.session.execute(
                    Select(func.count(SysUsers.id).label("total_lic")).where(SysUsers.type==usr["type"])
                ).first()
                if total is not None:
                    #A = Administrador, L = Lojista, I = Lojista (IA), R = Representante, V = Vendedor, C = Company User
                    if usr["type"]==UserType.ADMINISTRATOR.value and total.total_lic == int(plan.adm_licenses):
                        return {
                            "error_code": -1,
                            "error_details": "Número máximo de licenças Adm. atingido!",
                            "error_sql": ""
                        }
                    # elif usr["type"]==UserType.REPRESENTATIVE.value and total.total_lic == int(plan.repr_licenses):
                    #     return {
                    #         "error_code": -1,
                    #         "error_details": "Número máximo de licenças REP. atingido!",
                    #         "error_sql": ""
                    #     }
                    # elif usr["type"]==UserType.ISTORE.value and total.total_lic == int(plan.istore_licenses):
                    #     return {
                    #         "error_code": -1,
                    #         "error_details": "Número máximo de licenças I.A atingido!",
                    #         "error_sql": ""
                    #     }
                    # elif usr["type"]==UserType.STORE.value and total.total_lic == int(plan.store_licenses):
                    #     return {
                    #         "error_code": -1,
                    #         "error_details": "Número máximo de licenças Lojista/Empresa atingido!",
                    #         "error_sql": ""
                    #     }
                    elif usr["type"]==UserType.COMPANY_USER.value and total.total_lic == int(plan.user_licenses):
                        return {
                            "error_code": -1,
                            "error_details": "Número máximo de licenças Colaborador atingido!",
                            "error_sql": ""
                        }

                    user:SysUsers|None = SysUsers.query.get(int(usr["id"]))
                    if user is None:
                        user = SysUsers()
                        user.name     = usr["name"]
                        user.email    = usr["email"]
                        user.username = usr["username"]
                        user.password = usr["password"]
                        user.type     = usr["type"]
                        db.session.add(user)
                        db.session.commit()
                    else:
                        user.name     = usr["name"]
                        user.email    = usr["email"]
                        user.username = usr["username"]
                        user.password = usr["password"]
                        user.type     = usr["type"]
                        db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    @ns_user.response(HTTPStatus.OK,"Exclui os dados de um usuario")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @auth.login_required
    def delete(self)->bool|dict:
        try:
            req = request.get_json()
            for id in req["ids"]:
                usr:SysUsers|None = SysUsers.query.get(id)
                if usr is not None:
                    usr.active = req["toTrash"]
                    db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


@ns_user.route("/<int:id>")
@ns_user.param("id","Id do registro")
class UserApi(Resource):
    @ns_user.response(HTTPStatus.OK,"Obtem um registro de usuario",usr_model)
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @auth.login_required
    def get(self,id:int):
        try:
            rquery = Select(
                SysUsers.name,
                SysUsers.email,
                SysUsers.username,
                SysUsers.type,
                SysUsers.active,
                SysCustomerUser.id_customer,
                SysUsers.date_created,
                SysUsers.date_updated)\
                    .outerjoin(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
                    .where(SysUsers.id==id)
            
            # _show_query(rquery)
            user = db.session.execute(rquery).first()
            if user is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST

            return {
                "id": id,
                "name": user.name,
                "username": user.username,
                "email": user.email,
                "type": user.type,
                "active": user.active,
                "password": None,
                "date_created": user.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": user.date_updated.strftime("%Y-%m-%d %H:%M:%S") if user.date_updated is not None else None
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_user.response(HTTPStatus.OK,"Salva dados de um usuario")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            usr:SysUsers|None = SysUsers.query.get(id)
            if usr is not None:
                usr.name     = req["name"]
                usr.email    = req["email"]
                usr.username = req["username"]
                usr.password = usr.hash_pwd(req["password"])
                # usr.type     = req["type"]
                db.session.commit()

                #apaga para reconstruir o cadastro
                db.session.execute(Delete(SysCustomerUser).where(SysCustomerUser.id_user==id))
                db.session.commit()

                if req["id_customer"]!="undefined":
                    usrEn = SysCustomerUser()
                    setattr(usrEn,"id_user",id)
                    usrEn.id_customer = req["id_customer"]
                    db.session.add(usrEn)
                    db.session.commit()

            return True
        except exc.DatabaseError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_user.response(HTTPStatus.OK,"Exclui os dados de um usuario")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @auth.login_required
    def delete(self,id:int):
        try:
            usr:SysUsers|None = SysUsers.query.get(id)
            if usr is not None:
                setattr(usr,"active",False)
                db.session.commit()
                return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

class UserAuth(Resource):
    @ns_user.response(HTTPStatus.OK,"Realiza login e retorna o token")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    # @ns_user.param("username","Login do sistema","formData",required=True)
    # @ns_user.param("password","Senha do sistema","formData",required=True)
    def post(self):
        req = request.get_json()
        
        # busca os dados do usuario e da conta de customer deles atraves do usuario, email e CNPJ
        query = Select(SysUsers,SysCustomerUser)\
                     .join(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
                     .join(SysCustomer,SysCustomer.id==SysCustomerUser.id_customer)\
                     .where(SysUsers.active.is_(True))\
                     .where(or_(
                         SysUsers.username==req["username"],
                         SysUsers.email==req["username"],
                         SysCustomer.taxvat==str(request.form.get("username")).replace(".","").replace("-","").replace("/","")
                     ))
        usr = db.session.execute(query).first()
        
        # se o usuario existir
        if usr is not None:
            # dependendo do tipo ira buscas as entidades de negocio
            entity = 0
            if usr[0].type==UserType.STORE.value or usr[0].type==UserType.ISTORE.value or usr[0].type==UserType.REPRESENTATIVE:
                entity = db.session.execute(Select(CmmLegalEntities.id).where(CmmLegalEntities.id_user==usr[0].id)).first()

            # busca as configuracoes do usuario
            cfg = db.session.execute(Select(SysConfig).where(SysConfig.id_customer==str(usr[1].id_customer))).first()
            if cfg[0].dashboard_config=='M':
                dash_image = DashboardImage.MEN.value
                dash_color = DashboardImageColor.MEN.value
            if cfg[0].dashboard_config=='W':
                dash_image = DashboardImage.WOMEN.value
                dash_color = DashboardImageColor.WOMEN.value
            if cfg[0].dashboard_config=='H':
                dash_image = DashboardImage.WHEAT.value
                dash_color = DashboardImageColor.WHEAT.value
            if cfg[0].dashboard_config=='D':
                dash_image = DashboardImage.DRINK.value
                dash_color = DashboardImageColor.DRINK.value
            if cfg[0].dashboard_config=='S':
                dash_image = DashboardImage.SHOES.value
                dash_color = DashboardImageColor.SHOES.value
            if cfg[0].dashboard_config=='P':
                dash_image = DashboardImage.PISTON.value
                dash_color = DashboardImageColor.PISTON.value
            if cfg[0].dashboard_config=='F':
                dash_image = DashboardImage.PHARMA.value
                dash_color = DashboardImageColor.PHARMA.value

            #verifica a senha criptografada anteriormente
            pwd = str(req["password"]).encode()
            if usr[0].check_pwd(pwd):
                obj_retorno = {
					"token_access": usr[0].get_token(str(usr[1].id_customer)),
					"token_type": "Bearer",
					"token_expire": usr[0].token_expire.strftime("%Y-%m-%d %H:%M:%S"),
					"user_type": usr[0].type,
                    "id_user": usr[0].id,
                    "id_profile": str(usr[1].id_customer),
                    "id_entity": entity,
                    "config": {
                        "id_customer": str(cfg[0].id_customer),
                        "pagination_size": cfg[0].pagination_size,
                        "email_brevo_api_key": cfg[0].email_brevo_api_key,
                        "email_from_name": cfg[0].email_from_name,
                        "email_from_value": cfg[0].email_from_value,
                        "flimv_model": cfg[0].flimv_model,
                        "dashboard_config": cfg[0].dashboard_config,
                        "dashboard_image": dash_image,
                        "dashboard_color": dash_color,
                        "ai_model": cfg[0].ai_model,
                        "ai_api_key": cfg[0].ai_api_key,
                        "company_custom": cfg[0].company_custom,
                        "company_name": cfg[0].company_name,
                        "company_logo": cfg[0].company_logo,
                        "url_instagram": cfg[0].url_instagram,
                        "url_facebook": cfg[0].url_facebook,
                        "url_linkedin": cfg[0].url_linkedin,
                        "max_upload_files": cfg[0].max_upload_files,
                        "max_upload_images": cfg[0].max_upload_images,
                        "use_url_images": cfg[0].use_url_images,
                        "track_orders": cfg[0].track_orders,
                        "erp_integration": cfg[0].erp_integration,
                        "erp_url": cfg[0].erp_url,
                        "erp_token": cfg[0].erp_token,
                        "erp_grant_type": cfg[0].erp_grant_type,
                        "erp_client_id": cfg[0].erp_client_id,
                        "erp_client_secret": cfg[0].erp_client_secret,
                        "erp_username": cfg[0].erp_username,
                        "erp_password": cfg[0].erp_password
                    }
                }
                usr[0].is_authenticate = True
                db.session.commit()
                _save_customer_log(usr[0].id,usr[1].id_customer,CustomerAction.SYSTEM_ACCESS,'Efetuou login')
                return obj_retorno
            else:
                return 0 #senha invalida
        return -1 #usuario invalido
    
    @ns_user.response(HTTPStatus.OK,"Realiza a validacao do token do usuario")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao verificar o token!")
    def put(self) -> bool:
        try:
            #print(request.get_json())
            req = request.get_json()
            retorno = SysUsers.check_token(req['token'])
            return False if retorno is None else retorno.token_expire.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return False
    
    @ns_user.response(HTTPStatus.OK,"Realiza a atualizacao do token do usuario")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao atualizar o token!")
    def get(self):
        try:
            usr:SysUsers|None = SysUsers.query.get(request.args.get("id"))
            if usr is not None:
                usr.renew_token()
                db.session.commit()
                return usr.token_expire.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(e)
            return False
ns_user.add_resource(UserAuth,"/auth")

@ns_user.param("id","Id do registro")
class UserAuthLogout(Resource):
     @auth.login_required
     def post(self,id:int):
        try:
            usr:SysUsers|None = SysUsers.query.get(id)
            if usr is not None:
                usr.logout()
                db.session.commit()
                entity = SysCustomerUser.query.filter(SysCustomerUser.id_user==id).first()
                if entity is not None:
                    _save_customer_log(id,entity.id,CustomerAction.SYSTEM_ACCESS,'Efetuou logoff')
                return True
        except Exception:
            return False
        
ns_user.add_resource(UserAuthLogout,"/logout/<int:id>")


class UserUpdate(Resource):
    def __get_username(self,id,rule):
        reg = db.session.execute(Select(CmmLegalEntities.name).where(CmmLegalEntities.id==id)).first()
        if reg is not None:
            name = reg.name
            name = str(name).replace(".","")
            name = ''.join([i for i in name if not str(i).isdigit()])
            name = str(name.lower()\
                    .replace("ltda","")\
                    .replace("eireli","")\
                    .replace("'","")\
                    .replace("`","")\
                    .replace("´","")\
                    .replace("’","")\
                    .replace("”","")\
                    .replace("“","")).lstrip().rstrip()

            new_name = ""
            if rule=="FL": # first and last
                new_name = name.split(" ")[0]+"."+name.split(" ")[len(name.split(" "))-1]
            elif rule=="IL": # initial and last
                new_name = name.split(" ")[0][0:1]+"."+name.split(" ")[len(name.split(" "))-1]
            else: # first and initial
                new_name = name.split(" ")[0]+"."+name.split(" ")[len(name.split(" "))-1][0:1]

            return new_name

    @ns_user.response(HTTPStatus.OK,"Cria um ou mais novo(s) usuário(s) no sistema")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao criar!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            for id_entity in req["ids"]:

                #busca o total de licensas do plano
                plan = db.session.execute(
                    Select(SysPlan.adm_licenses,
                           SysPlan.user_licenses,
                           SysPlan.store_licenses,
                           SysPlan.istore_licenses,
                           SysPlan.repr_licenses
                        ).where(
                        SysPlan.id==(Select(SysCustomerPlan.id_plan).where(SysCustomerPlan.id_customer==request.headers.get('x-customer')  ))
                    )
                ).first()

                # busca o total de licencas existentes por tipo de usuario
                total = db.session.execute(
                    Select(func.count(SysUsers.id).label("total_lic")).where(SysUsers.type==usr["type"])
                ).first()
                if total is not None:
                    if usr["type"]==UserType.REPRESENTATIVE.value:
                        if plan.repr_licenses!=-1 and total.total_lic == int(plan.repr_licenses):
                            return {
                                "error_code": -1,
                                "error_details": "Número máximo de licenças REP. atingido!",
                                "error_sql": ""
                            }
                    elif usr["type"]==UserType.ISTORE.value:
                        if plan.istore_licenses!=-1 and total.total_lic == int(plan.istore_licenses):
                            return {
                                "error_code": -1,
                                "error_details": "Número máximo de licenças Lojista/Empresa (I.A) atingido!",
                                "error_sql": ""
                            }
                    elif usr["type"]==UserType.STORE.value and total.total_lic:
                        if plan.store_license!=-1 and int(plan.store_licenses):
                            return {
                                "error_code": -1,
                                "error_details": "Número máximo de licenças Lojista/Empresa atingido!",
                                "error_sql": ""
                            }


                # verifica se o usuario jah existe no sistema pelo username/email
                exist_user = db.session.execute(
                    Select(SysUsers.username,SysUsers.id)\
                    .where(SysUsers.email.in_(
                        Select(CmmLegalEntityContact.value).where(CmmLegalEntityContact.contact_type==LegalEntityContactType.EMAIL.value)
                    ))
                ).first()

    
                # se ainda nao existe usuario cria
                if exist_user is None:
                    usr = SysUsers()
                    setattr(usr,"username",(self.__get_username(id_entity,req["rule"])))
                    usr.hash_pwd(req["password"])
                    setattr(usr,"type",req["type"])
                    db.session.add(usr)
                    db.session.commit()

                    # adiciona o usuario para efetuar login no sistema
                    usrC = SysCustomerUser()
                    usrC.id_user   = usr.id
                    usrC.id_customer = request.headers.get("x-customer")
                    db.session.add(usrC)
                    db.session.commit()

                    # atualiza a tabela de entidades para receber o id do usuario
                    usrE:CmmLegalEntities = CmmLegalEntities.query.get(id_entity)
                    usrE.id_user = usr.id
                    db.session.commit()

                else:
                    # atualiza apenas o username e o password
                    usrE = db.session.execute(Select(SysCustomerUser.id_user).where(SysCustomerUser.id_customer==id_entity)).first()
                    usr:SysUsers|None = SysUsers.query.get(0 if usrE is None else usrE.id_user)
                    if usr is not None:
                        usr.hash_pwd(req["password"])
                        setattr(usr,"username",self.__get_username(id_entity,req["rule"]))
                        db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_user.add_resource(UserUpdate,'/massive-change')

# @ns_user.hide
class UserNew(Resource):
    @ns_user.response(HTTPStatus.OK,"Cria um novo usuário no sistema!")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao criar o usuário!")
    @ns_user.doc(body=usr_model)
    def post(self):
        try:
            req = request.get_json()

            usr = SysUsers.query.filter(SysUsers.username==req["username"]).first()
            if usr is not None:
                return {
                    "error_code": -1,
                    "error_details": "Usuário já cadastrado!",
                    "error_sql": ""
                }
            else:
                usr = SysUsers()
                usr.username = req["username"]
                usr.email    = req["email"]
                usr.name     = req["name"]
                usr.type     = req["type"]
                setattr(usr,"active",True)
                setattr(usr,"date_created",datetime.now())
                usr.password = req["password"]
                db.session.add(usr)
                db.session.commit()

                usrE = SysCustomerUser()
                usrE.id_user = usr.id
                usrE.id_customer = req["customer_id"]
                db.session.add(usrE)
                db.session.commit()

            return  True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_user.add_resource(UserNew,'/start')

class UserPassword(Resource):
    @ns_user.response(HTTPStatus.OK,"Gera uma nova senha padrão para um usuário!")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao atualizar!")
    def put(self):
        try:
            req = request.get_json()
            if req["password"] is None:
                pwd = str(environ.get("F2B_TOKEN_KEY")).lower()+str(datetime.now().year)
            else:
                pwd = str(req["password"])
            stmt = Select(SysUsers).where(SysUsers.id==req["id"])
            row = db.session.execute(stmt).first()
            usr: SysUsers | None = row[0] if row is not None else None
            if usr is not None:
                usr.hash_pwd(pwd)
                db.session.commit()
                return pwd
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_user.response(HTTPStatus.OK,"Busca o e-mail do usuario!")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao buscar!")    
    def patch(self):
        try:
            req = request.get_json()
            email = db.session.execute(Select(SysUsers.email).where(SysUsers.id==req["id_user"])).first()
            if email is not None:
                return {
                    "email": email.email
                }
            return None
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_user.response(HTTPStatus.OK,"Verifica se o e-mail existe no BD e envia mensagem para redefinição de senha!")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Falha ao atualizar!")
    def post(self):
        try:
            req = request.get_json()
            sended = False
            # so terah direito ao reset de senha se o usuario estiver ativo no sistema
            # o usuario eh desativado quando a entidade legal vai para a lixeira
            # porem o usuario tambem pode ser desativado diretamente no cadastro de 
            # usuarios
            exist = db.session.execute(
                Select(SysUsers.id,SysUsers.email,SysUsers.name,SysConfig.email_brevo_api_key,SysCustomerUser.id_customer)\
                .join(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
                .join(SysConfig,SysConfig.id_customer==SysCustomerUser.id_customer)\
                .where(and_(
                    SysUsers.active.is_(True),
                    SysUsers.email==req["email"]
                ))
            ).first()
            if exist is not None:
                sended = _send_email(
                    str(exist.id),
                    [exist.email],
                    [],
                    "Fast2bee - Recuperação de Senha",
                    exist.name,
                    MailTemplates.PWD_RECOVERY,
                    exist.email_brevo_api_key,
                    customer_id=str(exist.id_customer)+"/")
                return sended
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_user.add_resource(UserPassword,"/password/")

class UserCount(Resource):
    @ns_user.response(HTTPStatus.OK,"Retorna o total de Usuarios por tipo")
    @ns_user.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_user.param("type","Tipo da Entidade","query",type=str,enum=['','A','L','R','C'])
    @auth.login_required
    def get(self):
        try:
            stmt = Select(func.count(SysUsers.id).label("total")).select_from(SysUsers)\
            .join(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
            .where(SysCustomerUser.id_customer==request.headers.get("x-customer", None))
            if(request.args.get("level")!=""):
                stmt = stmt.where(SysUsers.type==request.args.get("level"))
            row = db.session.execute(stmt).first()
            return 0 if row is None else row.total
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_user.hide
    def post(self):
        try:
            req = request.get_json()
            stmt = Select(func.count(SysUsers.id).label("total")).select_from(SysUsers)\
            .join(SysCustomerUser,SysCustomerUser.id_user==SysUsers.id)\
            .where(SysCustomerUser.id_customer==request.headers.get("x-customer", None))
            if(req["level"]!=""):
                stmt = stmt.where(SysUsers.type==req["level"])
            row = db.session.execute(stmt).first()
            return 0 if row is None else row.total
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_user.add_resource(UserCount,'/count/')