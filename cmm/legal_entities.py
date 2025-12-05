import os
import csv
from auth import auth
from pathlib import Path
from flask import request
from http import HTTPStatus
from datetime import datetime
from f2bconfig import EntityAction, LegalEntityContactType
from models.helpers import _get_params, db
from models.tenant import CmmLegalEntities
from models.tenant import CmmLegalEntityContact
from flask_restx import Resource, Namespace, fields
from sqlalchemy import Delete, Select, and_,exc,asc,desc,func, or_
from models.tenant import _save_entity_log, B2bCustomerGroupCustomers 
from models.tenant import  B2bCustomerGroup, CmmLegalEntityHistory
from models.tenant import CmmLegalEntityFile,  CrmFunnelStageCustomer
from models.public import SysCities, SysCountries, SysStateRegions

ns_legal = Namespace("legal-entities",description="Operações para manipular dados de clientes/representantes")

lgl_pag_model = ns_legal.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Integer
    }
)

lgl_registry = ns_legal.model(
    "LegalEntityInsert",{
        "id":fields.Integer,
        "name":fields.String,
        "fantasy_name":fields.String,
        "id_city": fields.Integer,
        "taxvat": fields.String,
        "address": fields.String,
        "postal_code": fields.String,
        "neighborhood": fields.String,
        "type": fields.String
    }
)

lgl_model = ns_legal.model(
    "LegalEntity",{
        "id": fields.Integer,
        "name": fields.String,
        "taxvat": fields.String,
        "postal_code": fields.Integer,
        "neighborhood": fields.String,
        "type": fields.String(enum=['C','R','S']),
        "date_created": fields.DateTime,
        "date_updated": fields.DateTime
    }
)

lgl_return = ns_legal.model(
    "LegalEntitiesReturn",{
        "pagination": fields.Nested(lgl_pag_model),
        "data": fields.List(fields.Nested(lgl_model))
    }
)

####################################################################################
#            INICIO DAS CLASSES QUE IRAO TRATAR OS GRUPOS DE CLIENTES.             #
####################################################################################
@ns_legal.route("/")
class EntitysList(Resource):
    @ns_legal.response(HTTPStatus.OK,"Obtem a listagem de clientes/representantes",lgl_return)
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @ns_legal.param("page","Número da página de registros","query",type=int,required=True)
    @ns_legal.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_legal.param("query","Texto para busca","query")
    @ns_legal.param("list_all","Se deve exportar","query",type=bool,default=False)
    @auth.login_required
    def get(self):
        pag_num   = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size  = int(str(os.environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        search    = "" if request.args.get("query") is None else request.args.get("query")

        try:
            params = _get_params(search)
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc
            order_by  = 'id' if not hasattr(params,'order_by') else params.order_by if params is not None else 'id'
            trash     = False if not hasattr(params,"trash") else True
            list_all  = False if not hasattr(params,"list_all") else True

            filter_search = None if not hasattr(params,"search") else params.search if params is not None else None
            filter_type   = None if not hasattr(params,'type') else params.type if params is not None else None
            filter_rep    = None if not hasattr(params,'representative') else params.filter_rep if params is not None else None
            filter_country = None if not hasattr(params,'id_country') else params.id_country if params is not None else None
            filter_city    = None if not hasattr(params,"id_city") else params.id_city if params is not None else None
            filter_state_region = None if not hasattr(params,'id_state_region') else params.id_state_region if params is not None else None

            rquery = Select(
                    CmmLegalEntities.id,
                    CmmLegalEntities.name.label("social_name"),
                    CmmLegalEntities.fantasy_name,
                    CmmLegalEntities.postal_code,
                    CmmLegalEntities.neighborhood,
                    CmmLegalEntities.address,
                    CmmLegalEntities.taxvat,
                    CmmLegalEntities.type,
                    CmmLegalEntities.date_created,
                    CmmLegalEntities.date_updated,
                    SysCities.id.label("city_id"),
                    SysCities.name.label("city_name"),
                    SysCities.brazil_ibge_code,
                    SysStateRegions.id.label("state_id"),
                    SysStateRegions.name.label("state_name"),
                    SysStateRegions.acronym,
                    SysCountries.id.label("country_id"),
                    SysCountries.name.label("country_name"))\
                .outerjoin(SysCities,SysCities.id==CmmLegalEntities.id_city)\
                .outerjoin(SysStateRegions,SysStateRegions.id==SysCities.id_state_region)\
                .outerjoin(SysCountries,SysCountries.id==SysStateRegions.id_country)\
                .where(CmmLegalEntities.trash==trash)\
                .order_by(direction(getattr(CmmLegalEntities,order_by)))
            
            if filter_search is not None:
                rquery = rquery.where(
                    or_(
                        SysCountries.name.like("%{}%".format(filter_search)),
                        SysStateRegions.name.like("%{}%".format(filter_search)),
                        SysCities.name.like("%{}%".format(filter_search)),
                        CmmLegalEntities.name.like("%{}%".format(filter_search)),
                        CmmLegalEntities.fantasy_name.like("%{}%".format(filter_search)),
                        CmmLegalEntities.address.like("%{}%".format(filter_search)),
                        CmmLegalEntities.neighborhood.like("%{}%".format(filter_search)),
                        CmmLegalEntities.taxvat.like("%{}%".format(filter_search))
                    )
                )
                
            if filter_rep is not None:
                rquery = rquery.where(CmmLegalEntities.id.in_(
                    Select(B2bCustomerGroupCustomers.id_customer)\
                        .join(B2bCustomerGroup,B2bCustomerGroup.id==B2bCustomerGroupCustomers.id_customer_group)\
                        .where(B2bCustomerGroup.id_representative==filter_rep)
                ))
                
            if filter_type is not None:
                rquery = rquery.where(CmmLegalEntities.type==filter_type)

            if filter_city is not None:
                rquery = rquery.where(SysCities.id==filter_city)

            if filter_state_region is not None:
                rquery = rquery.where(SysStateRegions.id==filter_state_region)

            if filter_country is not None:
                rquery = rquery.where(SysCountries.id==filter_country)

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
                        "name": m.social_name,
                        "fantasy_name": m.fantasy_name,
                        "taxvat": m.taxvat,
                        "city": {
                            "id": m.city_id,
                            "name": m.city_name,
                            "stage_region": {
                                "id": m.state_id,
                                "name": m.state_name,
                                "acronym": m.acronym,
                                "country":{
                                    "id": m.country_id,
                                    "name": m.country_name
                                }
                            }
                        },
                        "postal_code": m.postal_code,
                        "address": m.address,
                        "neighborhood": m.neighborhood,
                        "type": m.type,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
            else:
                return [{
                        "id": m.id,
                        "name": m.social_name,
                        "fantasy_name": m.fantasy_name,
                        "taxvat": m.taxvat,
                        "city": {
                            "id": m.city_id,
                            "name": m.city_name,
                            "stage_region": {
                                "id": m.state_id,
                                "name": m.state_name,
                                "acronym": m.acronym,
                                "country":{
                                    "id": m.country_id,
                                    "name": m.country_name
                                }
                            }
                        },
                        "postal_code": m.postal_code,
                        "address": m.address,
                        "neighborhood": m.neighborhood,
                        "type": m.type,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery).all()]
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        except Exception as e:
            return  {
                "error_code": 0,
                "error_details": e.args,
                "error_sql": ""
            }        

    @ns_legal.response(HTTPStatus.OK,"Cria um novo registro de cliente/representante/fornecedor",model=lgl_registry)
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Falha ao criar um novo cliente/representante/fornecedor!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            cst = CmmLegalEntities()
            cst.name         = req["name"]
            cst.fantasy_name = req["fantasy_name"]
            cst.id_city      = req["city"]["id"]
            cst.taxvat       = req["taxvat"]
            cst.address      = req["address"]
            cst.postal_code  = req["postal_code"]
            cst.neighborhood = req["neighborhood"]
            cst.type         = req["type"]
            setattr(cst,"trash",False)
            setattr(cst,"activation_date",datetime.now())
            db.session.add(cst)
            db.session.commit()

            if req["agent"] is not None:
                grp = db.session.execute(Select(B2bCustomerGroup.id).where(B2bCustomerGroup.id_representative==req["agent"])).first()
                if grp is not None:
                    grpc = B2bCustomerGroupCustomers()
                    grpc.id_customer_group = grp.id
                    grpc.id_customer = cst.id
                    db.session.add(grpc)
                    db.session.commit()

            for contact in req["contacts"]:
                ct                 = CmmLegalEntityContact()
                ct.id_legal_entity = cst.id
                ct.name            = contact["name"]
                ct.contact_type    = contact["contact_type"]
                ct.value           = contact["value"]
                ct.is_default      = contact["is_default"]
                ct.is_whatsapp     = contact["is_whatsapp"]
                db.session.add(ct)

            db.session.commit()

            _save_entity_log(cst.id,EntityAction.DATA_REGISTERED,'Registro criado')  # type: ignore

            return cst.id
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    @ns_legal.response(HTTPStatus.OK,"Exclui os dados de um cliente/representante")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self):
        try:
            req = request.get_json()
            for id in req["ids"]:
                # move a(s) entidade(s) para a lixeira
                cst = CmmLegalEntities.query.get(id)
                setattr(cst,"trash",req["toTrash"])
                db.session.commit()

                # for usr in db.session.execute(Select(CmmUserEntity).where(CmmUserEntity.id_entity==id)):
                #     db.session.execute(
                #         Update(CmmUsers).values(active=(False if req["toTrash"]==1 else True)).where(CmmUsers.id==usr)
                #     )
                #     db.session.commit()

                _save_entity_log(id,EntityAction.DATA_DELETED,'Registro '+('movido para a' if req["toTrash"]==1 else 'removido da') +' Lixeira')
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


@ns_legal.route("/<int:id>")
class EntityApi(Resource):

    @ns_legal.response(HTTPStatus.OK,"Obtem um registro de cliente",lgl_model)
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @ns_legal.param("id","Id do usuário do sistema (tabela CmmUser)")
    @auth.login_required
    def get(self,id:int):
        try:
            rquery = Select(
                CmmLegalEntities.id,
                CmmLegalEntities.origin_id,
                CmmLegalEntities.name.label("social_name"),
                CmmLegalEntities.fantasy_name,
                CmmLegalEntities.postal_code,
                CmmLegalEntities.address,
                CmmLegalEntities.neighborhood,
                CmmLegalEntities.taxvat,
                CmmLegalEntities.type,
                CmmLegalEntities.date_created,
                CmmLegalEntities.date_updated,
                SysCities.id.label("city_id"),
                SysCities.name.label("city_name"),
                SysCities.brazil_ibge_code,
                SysStateRegions.id.label("state_id"),
                SysStateRegions.name.label("state_name"),
                SysStateRegions.acronym,
                SysCountries.id.label("country_id"),
                SysCountries.name.label("country_name"))\
            .join(SysCities,SysCities.id==CmmLegalEntities.id_city)\
            .join(SysStateRegions,SysStateRegions.id==SysCities.id_state_region)\
            .join(SysCountries,SysCountries.id==SysStateRegions.id_country)\
            .where(CmmLegalEntities.id==id)

            m = db.session.execute(rquery).first()
            if m is None:
                return {
                        "error_code": HTTPStatus.BAD_REQUEST.value,
                        "error_details": "Registro não encontrado!",
                        "error_sql": ""
                    }, HTTPStatus.BAD_REQUEST

            return {
                    "id": m.id,
                    "origin_id": m.origin_id,
                    "name": m.social_name,
                    "fantasy_name": m.fantasy_name,
                    "taxvat": m.taxvat,
                    "city": {
                        "id": m.city_id,
                        "name": m.city_name,
                        "brazil_ibge_code": m.brazil_ibge_code,
                        "state_region": {
                            "id": m.state_id,
                            "name": m.state_name,
                            "acronym": m.acronym,
                            "country":{
                                "id": m.country_id,
                                "name": m.country_name
                            }
                        }
                    },
                    "agent": self.__get_representative((m.id)),
                    "contacts": self.__get_contacts((m.id)),
                    "files": self.__get_file((m.id)),
                    "postal_code": m.postal_code,
                    "neighborhood": m.neighborhood,
                    "address": m.address,
                    "type": m.type,
                    "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None,
                }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    def __get_contacts(self,id_customer:int):
        stmt = Select(CmmLegalEntityContact.id,
                      CmmLegalEntityContact.name,
                      CmmLegalEntityContact.contact_type,
                      CmmLegalEntityContact.value,
                      CmmLegalEntityContact.is_whatsapp,
                      CmmLegalEntityContact.is_default)\
            .where(CmmLegalEntityContact.id_legal_entity==id_customer)
        
        return [{
            "id": c.id,
            "id_legal_entity": id_customer,
            "name": c.name,
            "contact_type": c.contact_type,
            "value": c.value,
            "is_whatsapp": c.is_whatsapp, #E = E-mail, P = Phone
            "is_default": c.is_default
        } for c in db.session.execute(stmt)]
    
    def __get_file(self,id_customer:int):
        stmt = Select(CmmLegalEntityFile.id,
                      CmmLegalEntityFile.name,
                      CmmLegalEntityFile.folder,
                      CmmLegalEntityFile.content_type
                      ).where(CmmLegalEntityFile.id_legal_entity==id_customer)
        return [{
            "id": c.id,
            "name": c.name,
            "folder": c.folder,
            "content_type":c.content_type
        }for c in db.session.execute(stmt)]
    
    def __get_representative(self,id:int):
        try:
            rquery = Select(
                    CmmLegalEntities.id,
                    CmmLegalEntities.origin_id,
                    CmmLegalEntities.name.label("social_name"),
                    CmmLegalEntities.fantasy_name,
                    CmmLegalEntities.postal_code,
                    CmmLegalEntities.neighborhood,
                    CmmLegalEntities.address,
                    CmmLegalEntities.taxvat,
                    CmmLegalEntities.type,
                    CmmLegalEntities.date_created,
                    CmmLegalEntities.date_updated,
                    SysCities.id.label("city_id"),
                    SysCities.name.label("city_name"),
                    SysCities.brazil_ibge_code,
                    SysStateRegions.id.label("state_id"),
                    SysStateRegions.name.label("state_name"),
                    SysStateRegions.acronym,
                    SysCountries.id.label("country_id"),
                    SysCountries.name.label("country_name"))\
                .join(SysCities,SysCities.id==CmmLegalEntities.id_city)\
                .join(SysStateRegions,SysStateRegions.id==SysCities.id_state_region)\
                .join(SysCountries,SysCountries.id==SysStateRegions.id_country)\
                .join(B2bCustomerGroup,B2bCustomerGroup.id_representative==CmmLegalEntities.id)\
                .where(and_(CmmLegalEntities.trash.is_(False),B2bCustomerGroupCustomers.id_customer==id))
            
            m = db.session.execute(rquery).first()
            if m is None:
                return {
                        "error_code": HTTPStatus.BAD_REQUEST.value,
                        "error_details": "Registro não encontrado!",
                        "error_sql": ""
                    }, HTTPStatus.BAD_REQUEST

            return {
                    "id": m.id,
                    "origin_id": m.origin_id,
                    "name": m.social_name,
                    "fantasy_name": m.fantasy_name,
                    "taxvat": m.taxvat,
                    "city": {
                        "id": m.city_id,
                        "name": m.city_name,
                        "brazil_ibge_code":m.brazil_ibge_code,
                        "state_region": {
                            "id": m.state_id,
                            "name": m.state_name,
                            "acronym": m.acronym,
                            "country":{
                                "id": m.country_id,
                                "name": m.country_name
                            }
                        }
                    },
                    "contacts": self.__get_contacts(m.id),
                    "files": self.__get_file(m.id),
                    "postal_code": m.postal_code,
                    "neighborhood": m.neighborhood,
                    "address": m.address,
                    "type": m.type,
                    "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_updated": (m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None)
                }
        except Exception:
            return None

    @ns_legal.response(HTTPStatus.OK,"Salva dados de um cliente/representante/fornecedor",model=lgl_registry)
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            cst:CmmLegalEntities|None = CmmLegalEntities.query.get(id)
            if cst is not None:
                cst.name         = req["name"]
                cst.fantasy_name = req["fantasy_name"]
                cst.id_city      = req["city"]["id"]
                cst.taxvat       = req["taxvat"]
                cst.address      = req["address"]
                cst.postal_code  = req["postal_code"]
                cst.neighborhood = req["neighborhood"]
                cst.type         = req["type"]
                setattr(cst,"date_updated",datetime.now())
                db.session.commit()

                #limpa o que existe no grupo para nao gerar duplicacao de chave
                db.session.execute(Delete(B2bCustomerGroupCustomers).where(B2bCustomerGroupCustomers.id_customer==id))
                db.session.commit()

                if req["agent"] is not None:
                    grp = db.session.execute(Select(B2bCustomerGroup.id).where(B2bCustomerGroup.id_representative==req["agent"])).first()
                    if grp is not None:
                        grpc = B2bCustomerGroupCustomers()
                        grpc.id_customer_group = grp.id
                        grpc.id_customer = cst.id
                        db.session.add(grpc)
                        db.session.commit()

                for contact in req["contacts"]:
                    if contact["id"] == 0:
                        ct                 = CmmLegalEntityContact()
                        ct.id_legal_entity = cst.id
                        ct.name            = contact["name"]
                        ct.contact_type    = contact["contact_type"]
                        ct.value           = contact["value"]
                        ct.is_default      = contact["is_default"]
                        ct.is_whatsapp     = contact["is_whatsapp"]
                        db.session.add(ct)
                        db.session.commit()
                    else:
                        ct:CmmLegalEntityContact|None = CmmLegalEntityContact.query.get(contact["id"])
                        if ct is not None:
                            ct.name         = contact["name"]
                            ct.contact_type = contact["contact_type"]
                            ct.value        = contact["value"]
                            ct.is_default   = contact["is_default"]
                            ct.is_whatsapp  = contact["is_whatsapp"]
                            db.session.commit()
                
                _save_entity_log(id,EntityAction.DATA_UPDATED,'Registro alterado')

                return id
            return 0
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_legal.response(HTTPStatus.OK,"Exclui os dados de um cliente/representante")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_legal.param("id","Id do registro")
    @auth.login_required
    def delete(self,id:int)->bool|dict:
        try:
            cst = CmmLegalEntities.query.get(id)
            setattr(cst,"trash",True)
            db.session.commit()
            _save_entity_log(id,EntityAction.DATA_DELETED,'Registro arquivado')
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

class EntityCount(Resource):
    @ns_legal.response(HTTPStatus.OK,"Retorna o total de Entidades por tipo")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_legal.param("type","Tipo da Entidade","query",type=str,enum=['C','R','S'])
    @auth.login_required
    def get(self):
        try:
            stmt = Select(func.count(CmmLegalEntities.id).label("total")).select_from(CmmLegalEntities).where(CmmLegalEntities.type==request.args.get("type"))
            result = db.session.execute(stmt).first()
            total  = 0 if result is None or result.total is None else result.total
            return total
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_legal.add_resource(EntityCount,'/count')

class EntityOfStage(Resource):
    @ns_legal.response(HTTPStatus.OK,"Retorna o total de Entidades por tipo")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_legal.param("page","Número da página de registros","query",type=int,required=True)
    @ns_legal.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_legal.param("query","Número de registros por página","query",type=str)
    @auth.login_required
    def get(self,id:int):
        pag_num   = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size  = int(str(os.environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))

        try:
            params = _get_params(request.args.get("query"))
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc
            order_by  = 'id' if not hasattr(params,'order_by') else params.order_by if params is not None else 'id'
            search    = None if not hasattr(params,"search") else params.search

            rquery = Select(
                CmmLegalEntities.id,
                CmmLegalEntities.name.label("social_name"),
                CmmLegalEntities.fantasy_name,
                CmmLegalEntities.postal_code,
                CmmLegalEntities.address,
                CmmLegalEntities.neighborhood,
                CmmLegalEntities.taxvat,
                CmmLegalEntities.type,
                CmmLegalEntities.date_created,
                CmmLegalEntities.date_updated,
                SysCities.id.label("city_id"),
                SysCities.name.label("city_name"),
                SysCities.brazil_ibge_code,
                SysStateRegions.id.label("state_id"),
                SysStateRegions.name.label("state_name"),
                SysStateRegions.acronym,
                SysCountries.id.label("country_id"),
                SysCountries.name.label("country_name"))\
            .join(SysCities,SysCities.id==CmmLegalEntities.id_city)\
            .join(SysStateRegions,SysStateRegions.id==SysCities.id_state_region)\
            .join(SysCountries,SysCountries.id==SysStateRegions.id_country)\
            .join(CrmFunnelStageCustomer,CrmFunnelStageCustomer.id_customer==CmmLegalEntities.id)\
            .where(CrmFunnelStageCustomer.id_funnel_stage==id)\
            .order_by(direction(getattr(CmmLegalEntities,order_by)))

            #_show_query(rquery)

            if search is not None:
                rquery = rquery.where(
                    or_(
                        SysCountries.name.like("%{}%".format(search)),
                        SysStateRegions.name.like("%{}%".format(search)),
                        SysCities.name.like("%{}%".format(search)),
                        CmmLegalEntities.name.like("%{}%".format(search)),
                        CmmLegalEntities.fantasy_name.like("%{}%".format(search)), 
                        CmmLegalEntities.neighborhood.like("%{}%".format(search)),
                        CmmLegalEntities.id.in_(
                            Select(CmmLegalEntityContact.id_legal_entity)\
                            .where(
                                or_(
                                    CmmLegalEntityContact.name.like("%{}%".format(search)),
                                    CmmLegalEntityContact.value.like("%{}%".format(search))
                                )
                            )
                        )
                    )
                )
                
            pag = db.paginate(rquery,page=pag_num,per_page=pag_size)

            rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)

            return {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next,
                    },
                    "data":[{
                        "id": m.id,
                        "name": m.social_name,
                        "fantasy_name": m.fantasy_name,
                        "taxvat": m.taxvat,
                        "city": {
                            "id": m.city_id,
                            "name": m.city_name,
                            "brazil_ibge_code":m.brazil_ibge_code,
                            "state_region": {
                                "id": m.state_id,
                                "name": m.state_name,
                                "acronym": m.acronym,
                                "country":{
                                    "id": m.country_id,
                                    "name": m.country_name
                                }
                            }
                        },
                        "contacts": self.__get_contacts(m.id),
                        "files": self.__get_file(m.id),
                        "postal_code": m.postal_code,
                        "address": m.address,
                        "neighborhood": m.neighborhood,
                        "type": m.type,
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    def __get_contacts(self,id_customer:int):
        stmt = Select(CmmLegalEntityContact.id,
                      CmmLegalEntityContact.name,
                      CmmLegalEntityContact.contact_type,
                      CmmLegalEntityContact.value,
                      CmmLegalEntityContact.is_whatsapp,
                      CmmLegalEntityContact.is_default)\
            .where(CmmLegalEntityContact.id_legal_entity==id_customer)
        
        return [{
            "id": c.id,
            "id_legal_entity": id_customer,
            "name": c.name,
            "contact_type": c.contact_type,
            "value": c.value,
            "is_whatsapp": c.is_whatsapp, #E = E-mail, P = Phone
            "is_default": c.is_default
        } for c in db.session.execute(stmt)]
    
    def __get_file(self,id_customer:int):
        stmt = Select(CmmLegalEntityFile.id,
                      CmmLegalEntityFile.name,
                      CmmLegalEntityFile.folder,
                      CmmLegalEntityFile.content_type
                      ).where(CmmLegalEntityFile.id_legal_entity==id_customer)
        return [{
            "id": c.id,
            "name": c.name,
            "folder": c.folder,
            "content_type":c.content_type
        }for c in db.session.execute(stmt)]

    @ns_legal.response(HTTPStatus.OK,"Adiciona um ou mais clientes em um estagio de um funil")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Falha ao adicionar cliente!")
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            for entity in req["entities"]:
                #verifica se ja ha registro
                exist = db.session.execute(
                    Select(func.count().label("total")).select_from(CrmFunnelStageCustomer).where(
                        and_(
                            CrmFunnelStageCustomer.id_customer==entity["id"],
                            CrmFunnelStageCustomer.id_funnel_stage==id
                        )
                    )
                ).first()

                if exist is None or exist.total == 0:
                    crm = CrmFunnelStageCustomer()
                    crm.id_customer = entity["id"]
                    setattr(crm,"id_funnel_stage",id)
                    db.session.add(crm)
            db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_legal.add_resource(EntityOfStage,'/by-crm-stage/<int:id>')

class EntityContact(Resource):
    @ns_legal.response(HTTPStatus.OK,"Salva contato(s) de uma entidade")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Falha ao salvar o(s) registro(s)!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            #print(req)
            for r in req:
                if r["id"]==0:
                    ct = CmmLegalEntityContact()
                    setattr(ct,"id",0)
                else:
                    ct:CmmLegalEntityContact = CmmLegalEntityContact().query.get(r["id"]) # type: ignore

                ct.id_legal_entity = r['id_legal_entity']
                ct.name            = r['name']
                ct.contact_type    = r['contact_type']
                ct.is_default      = r['is_default']
                ct.is_whatsapp     = r['is_whatsapp']
                ct.value           = r['value']
                if r["id"] == 0:
                    _save_entity_log(r['id_legal_entity'],EntityAction.DATA_REGISTERED,'Adicionado contato '+r['name'])
                    db.session.add(ct)
                else:
                    _save_entity_log(r['id_legal_entity'],EntityAction.DATA_UPDATED,'Atualizado contato '+r['name'])
                db.session.commit()
                return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_legal.response(HTTPStatus.OK,"Exclui contato(s) de uma entidade")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self):
        try:
            req = request.get_json()
            for contact in req:
                db.session.execute(Delete(CmmLegalEntityContact).where(CmmLegalEntityContact.id==contact["id"]))
                db.session.commit()
                return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
ns_legal.add_resource(EntityContact,'/save-contacts')

class EntityHistory(Resource):
    @ns_legal.response(HTTPStatus.OK,"Obtem os dados históricos de uma entidade")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    @ns_legal.param("page","Número da página de registros","query",type=int,required=True)
    @ns_legal.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_legal.param("query","Texto para busca","query")
    @auth.login_required
    def get(self,id:int):
        pag_num   = 1 if request.args.get("page") is None or request.args.get("page")==0 else int(str(request.args.get("page")))
        pag_size  = int(str(os.environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        search    = "" if request.args.get("query") is None else request.args.get("query")
        try:
            params = _get_params(search)
            search = None
            if params is not None:
                search = params.search

            rquery = Select(CmmLegalEntityHistory.id,
                            CmmLegalEntityHistory.id_legal_entity,
                            CmmLegalEntityHistory.history,
                            CmmLegalEntityHistory.action,
                            CmmLegalEntityHistory.date_created)\
                            .where(CmmLegalEntityHistory.id_legal_entity==id)
            
            if search is not None:
                rquery = rquery.where(CmmLegalEntityHistory.history.like('%{}%'.format(search)))
            

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
                        "id": r.id,
                        "id_legal_entity": r.id_legal_entity,
                        "history": r.history,
                        "action": r.action,
                        "date_created": r.date_created.strftime("%d/%m/%Y %H:%M:%S")
                    }for r in db.session.execute(rquery)]
            }
            
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_legal.response(HTTPStatus.OK,"Adiciona um comentário no histórico de uma entidade")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado")
    def post(self,id:int):
        try:
            req = request.get_json()
            _save_entity_log(id,EntityAction.COMMENT_ADDED,'Adicionado comentário: '+req)
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

ns_legal.add_resource(EntityHistory,'/history/<int:id>')


class EntityImport(Resource):
    @ns_legal.response(HTTPStatus.OK,"Realiza o pocessamento dos registros do arquivo de importacao")
    @ns_legal.response(HTTPStatus.BAD_REQUEST,"Falha ao processar registros")
    def post(self):
        try:
            customer    = request.headers.get("x-customer")

            #varre o diretorio atras dos arquivos do customer
            str_path = str(os.environ.get("F2B_APP_PATH"))+'assets/import/'
            path = Path(str_path)
            for file in list(path.rglob("*.csv")):
                if file.name.find(customer)!=-1:
                    "extract data from file name"
                    data = file.name.split("_")
                    # tipo de cadastro
                    # data[2]

                    with open(str_path+file.name,mode='r',newline='',encoding="utf-8") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if reader.line_num > 1:
                                self.__import(row,data[2])

                    # apaga o arquivo apos importacao
                    if os.path.exists(str_path+file.name)==True:
                        os.remove(str_path+file.name)
            
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
        
    def __import(self,reg:list,type:str) -> bool:
                
        ent = CmmLegalEntities()
        ent.origin_id    = reg[0]
        ent.taxvat       = reg[1]
        ent.name         = reg[2]
        ent.fantasy_name = reg[3]
        ent.type         = type

        city = db.session.execute(Select(SysCities.id).where(func.upper(SysCities.name)==str(reg[4]).upper())).first()
        ent.id_city         = 0 if city is None else city.id
        ent.postal_code     = str(reg[5]).replace("-","").replace(" ","")
        ent.neighborhood    = str(reg[6]).upper()
        ent.address         = str(reg[7]).upper()
        ent.activation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.session.add(ent)
        db.session.commit()

        ent_ct = CmmLegalEntityContact()
        ent_ct.id_legal_entity = ent.id
        ent_ct.name            = str(reg[8])
        ent_ct.contact_type    = LegalEntityContactType.PHONE.value
        ent_ct.value           = str(reg[9]).replace(" ","").replace("-","").replace("(","").replace(")","") # se for telefone pode remover tracos e parenteses
        ent_ct.is_whatsapp     = True if reg[10]=="1" else False
        ent_ct.is_default      = True if reg[11]=="1" else False
        db.session.add(ent_ct)

        ent_ml = CmmLegalEntityContact()
        ent_ml.id_legal_entity = ent.id
        ent_ml.name            = reg[12]
        ent_ml.contact_type    = LegalEntityContactType.EMAIL.value
        ent_ml.value           = reg[13]
        ent_ml.is_whatsapp     = False
        ent_ml.is_default      = True if reg[14]=="1" else False
        db.session.add(ent_ml)
        db.session.commit()

        return True



ns_legal.add_resource(EntityImport,'/process-import')