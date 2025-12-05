import calendar
import simplejson
from auth import auth
from os import environ
from flask import request
import simplejson as json
from decimal import Decimal
from http import HTTPStatus
from datetime import datetime,date
from f2bconfig import CrmFunnelType
from models.helpers import _get_params, _show_query, db
from models.tenant import ScmEvent, ScmEventType
from flask_restx import Resource, Namespace, fields
from sqlalchemy import desc, exc, asc,between,Select,and_, func, or_
from models.tenant import CrmConfig, CrmFunnel, CrmFunnelStage 
from models.tenant import B2bBrand, B2bCollection, ScmCalendar

ns_calendar = Namespace("calendar",description="Operações para manipular dados de cidades")

evt_model = ns_calendar.model(
    "Event",{
        "name": fields.String,
        "start": fields.Date,
        "end": fields.Date,
        "type": fields.String
    }
)

def get_children(p_id_parent:int):
    yquery = Select(ScmEvent.id,
                    ScmEvent.id_parent,
                    ScmEvent.name,
                    ScmEvent.year,
                    ScmEvent.start_date,
                    ScmEvent.end_date,
                    ScmEvent.budget_value,
                    ScmEvent.date_created,
                    ScmEvent.date_updated,
                    ScmEventType.id.label("id_event_type"),
                    ScmEventType.name.label("event_type_name"),
                    ScmEventType.hex_color,
                    ScmEventType.has_budget,
                    ScmEventType.is_milestone,
                    B2bCollection.id.label("id_collection"),
                    B2bCollection.name.label("collection_name"),
                    B2bBrand.id.label("id_brand"),
                    B2bBrand.name.label("brand_name")).distinct()\
            .join(ScmEventType,ScmEventType.id==ScmEvent.id_event_type)\
            .join(ScmCalendar,and_(ScmEvent.year==ScmCalendar.year,ScmEvent.start_date==ScmCalendar.calendar_date))\
            .outerjoin(B2bCollection,ScmEvent.id_collection==B2bCollection.id)\
            .outerjoin(B2bBrand,B2bCollection.id_brand==B2bBrand.id)\
            .where(ScmEvent.id_parent==p_id_parent)\
            .order_by(asc(ScmEvent.start_date))
    
    return [{
        "id": e.id,
        "id_parent": e.id_parent,
        "name": e.name,
        "start_week": date(e.start_date.year,e.start_date.month,e.start_date.day).isocalendar().week,
        "end_week": date(e.end_date.year,e.end_date.month,e.end_date.day).isocalendar().week,
        "start_date": e.start_date.strftime("%Y-%m-%d"),
        "end_date": e.end_date.strftime("%Y-%m-%d"),
        "year":e.year,
        "budget_value": None if e.budget_value is None else json.dumps(e.budget_value),
        "date_created": e.date_created.strftime("%Y-%m-%d %H:%M:%S"),
        "date_updated": e.date_updated.strftime("%Y-%m-%d %H:%M:%S") if e.date_updated is not None else None,
        "type": {
            "id": e.id_event_type,
            "name": e.event_type_name,
            "hex_color": e.hex_color,
            "has_budget": e.has_budget,
            "is_milestone": e.is_milestone
        },
        "collection":{
            "id":e.id_collection,
            "name": e.collection_name,
            "brand":{
                "id": e.id_brand,
                "name": e.brand_name
            }
        }
    } for e in db.session.execute(yquery).all()]

@ns_calendar.route("/")
class CalendarList(Resource):
    @ns_calendar.response(HTTPStatus.OK,"Obtem a listagem de dados ano/mes/semanas do calendario")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @ns_calendar.param("query","Texto para busca de intervalos de datas e eventos","query")
    @auth.login_required
    def get(self):
        search = "" if request.args.get("query") is None else request.args.get("query")

        try:
            params = _get_params(search)
            if params is not None:
                if params.start=="" and params.end=="":
                    # tenta buscar eventos do calendario com maior data de fim
                    last_date = db.session.execute(
                        Select(ScmEvent.end_date).order_by(desc(ScmEvent.end_date))
                    ).first()
                    if last_date is None:
                        params.end = date(datetime.now().year,12,31)
                    else:
                        # obtem o ultimo dia do mes da data do maior evento
                        _,num_days = calendar.monthrange(last_date.end_date.year,last_date.end_date.month)
                        if num_days > last_date.end_date.day:
                            params.end = datetime(last_date.end_date.year,last_date.end_date.month,num_days).date()
                        else:
                            params.end = last_date.end_date
                    params.start = date(datetime.now().year,1,1)
                    

                yquery = Select(ScmCalendar.year).distinct()\
                    .where(between(ScmCalendar.calendar_date,params.start,params.end))\
                    .where(ScmCalendar.day_of_week==7)
                    # .order_by(asc(ScmCalendar.time_id))

                retorno = [{
                        "year": y.year,
                        "months": [{
                            "position": m.month,
                            "weeks": self.__get_weeks(params.start,params.end,y.year,m.month)
                        }for m in self.__get_months(params.start,params.end,y.year)],
                    } for y in db.session.execute(yquery).all()]
                return retorno
            return None
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    def __get_months(self,dt_start,dt_end,_current_year):
        return db.session.execute(Select(ScmCalendar.month).distinct()\
            .where(between(ScmCalendar.calendar_date,dt_start,dt_end))\
            .where(ScmCalendar.year==_current_year)\
            .where(ScmCalendar.day_of_week==7)
            #.order_by(asc(ScmCalendar.time_id))
        ).all()
    
    def __get_weeks(self,dt_start,dt_end,_current_year,_current_month):
        weeks = []
        qry = Select(ScmCalendar.week).distinct()\
            .where(ScmCalendar.calendar_date.between(dt_start,dt_end))\
            .where(and_(ScmCalendar.year==_current_year,ScmCalendar.month==_current_month,ScmCalendar.day_of_week==7))
            # .order_by(asc(ScmCalendar.time_id))
        # _show_query(qry)
        for w in db.session.execute(qry).all():
            weeks.append(w.week)
        return weeks

    @ns_calendar.response(HTTPStatus.OK,"Salva um evento no calendário",evt_model)
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Falha salvar registro!")
    @auth.login_required
    def post(self):
        try:
            req = request.get_json()
            date_start = datetime.strptime(req["date_start"],"%Y-%m-%d").date()
            date_end   = datetime.strptime(req["date_end"],"%Y-%m-%d").date()

            reg = ScmEvent()
            reg.name          = req["name"]
            setattr(reg,"id_parent",(None if req["id_parent"] is None or req["id_parent"]=="" else req["id_parent"]))
            setattr(reg,"year",date_start.year)
            setattr(reg,"start_date",date_start)
            setattr(reg,"end_date",date_end)
            reg.id_event_type = req["id_event_type"]
            setattr(reg,"id_collection",(None if req["id_collection"] is None or req["id_collection"]=="" else req["id_collection"]))
            setattr(reg,"budget_value",(None if req["budget_value"] is None or req["budget_value"]=="" else req["budget_value"]))
            db.session.add(reg)
            db.session.commit()

            # verificar e criar o funil no calendario
            evtType:ScmEventType|None = ScmEventType.query.get(req["id_event_type"])
            if evtType is not None:
                if evtType.create_funnel is True:
                    # verifica se foi indicada a colecao
                    if req["id_collection"] is not None:
                        col:B2bCollection|None = B2bCollection.query.get(req["id_collection"])
                        exist = db.session.execute(Select(func.count().label("total")).where(CrmFunnel.name=="SYS - "+('' if col is None else col.name))).first()

                        # verifica se jah existe um funil com esse nome
                        if exist is None or exist.total == 0:
                            # busca a configuracao do CRM
                            crm_cfg = db.session.execute(
                                Select(CrmConfig.cfg_value).where(CrmConfig.cfg_name=='DEFAULT_FUNNEL_STAGES')
                            ).first()

                            # cria o funil com o nome da colecao
                            fun:CrmFunnel = CrmFunnel()
                            setattr(fun,"name","SYS - "+str('' if col is None else col.name))
                            setattr(fun,"is_default",False)
                            setattr(fun,"type",CrmFunnelType.SALES.value)
                            db.session.add(fun)
                            db.session.commit()

                            for stg in str('' if crm_cfg is None else crm_cfg.cfg_value).split(","):
                                cfg_stg:CrmFunnelStage|None = CrmFunnelStage.query.get(stg)
                                new_stg = CrmFunnelStage()
                                new_stg.id_funnel  = fun.id
                                setattr(new_stg,"name",'' if cfg_stg is None else cfg_stg.name)
                                setattr(new_stg,"icon",'' if cfg_stg is None else cfg_stg.icon)
                                setattr(new_stg,"icon_color",'' if cfg_stg is None else cfg_stg.icon_color)
                                setattr(new_stg,"color",'' if cfg_stg is None else cfg_stg.color)
                                setattr(new_stg,"order",'' if cfg_stg is None else cfg_stg.order)
                                db.session.add(new_stg)
                            db.session.commit()

            return reg.id
            
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_calendar.response(HTTPStatus.OK,"Exclui os dados de varios eventos")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self):
        try:
            req = request.get_json()
            for r in req:
                it = ScmEvent.query.get(r)
                db.session.delete(it)
                db.session.commit()
            
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

@ns_calendar.route("/<int:id>")
@ns_calendar.param("id","Id do registro")
class CalendarEventApi(Resource):
    @ns_calendar.response(HTTPStatus.OK,"Retorna os dados de um evento especifico")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self,id:int):
        try:
            qry = ScmEvent.query.get(id)
            if qry is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST

            return {
                "id": qry.id,
                "id_parent": qry.id_parent,
                "name": qry.name,
                "year": qry.year,
                "start_week": date(qry.start_date.year,qry.start_date.month,qry.start_date.day).isocalendar().week,
                "end_week": date(qry.end_date.year,qry.end_date.month,qry.end_date.day).isocalendar().week,
                "start_date": qry.start_date,
                "end_date": qry.end_date,
                "id_event_type": qry.id_event_type,
                "id_collection": qry.id_collection,
                "budget_value": qry.budget_value,
                "date_created": qry.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": None if qry.date_updated is None else qry.date_updated.strftime("%Y-%m-%d %H:%M:%S")
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_calendar.response(HTTPStatus.OK,"Atualiza os dados de um evento")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_calendar.doc(body=evt_model)
    @auth.login_required
    def post(self,id:int):
        try:
            req = request.get_json()
            date_start = datetime.strptime(req["date_start"],"%Y-%m-%d")
            date_end   = datetime.strptime(req["date_end"],"%Y-%m-%d")

            reg:ScmEvent|None = ScmEvent.query.get(id)
            setattr(reg,"name",('' if req is None else req["name"]))
            setattr(reg,"id_parent",(0 if req is None else req["id_parent"]))
            setattr(reg,"year",(None if req is None else date_start.year))
            setattr(reg,"start_date",(None if req is None else date_start))
            setattr(reg,"end_date",(None if req is None else date_end))
            setattr(reg,"id_event_type",(None if req is None else req["id_event_type"]))
            setattr(reg,"id_collection",(None if req["id_collection"] is None else req["id_collection"]))
            setattr(reg,"budget_value",(None if req["budget_value"] is None else req["budget_value"]))
            db.session.commit()

            # verificar e criar o funil no calendario
            evtType:ScmEventType|None = ScmEventType.query.get(req["id_event_type"])
            if evtType is not None and evtType.create_funnel is True:
                # verifica se foi indicada a colecao
                if req["id_collection"] is not None:
                    col:B2bCollection|None = B2bCollection.query.get(req["id_collection"])
                    exist = db.session.execute(Select(func.count().label("total")).where(CrmFunnel.name=="SYS - "+('' if col is None else col.name))).first()

                    # verifica se jah existe um funil com esse nome
                    if exist is None or exist.total == 0:
                        # busca a configuracao do CRM
                        crm_cfg = db.session.execute(
                            Select(CrmConfig.cfg_value).where(CrmConfig.cfg_name=='DEFAULT_FUNNEL_STAGES')
                        ).first()

                        # cria o funil com o nome da colecao
                        fun = CrmFunnel()
                        setattr(fun,"name",("SYS - "+('' if col is None else col.name)))
                        setattr(fun,"is_default",False)
                        setattr(fun,"type",CrmFunnelType.SALES.value)
                        db.session.add(fun)
                        db.session.commit()

                        for stg in str('' if crm_cfg is None else crm_cfg.cfg_value).split(","):
                            cfg_stg = CrmFunnelStage.query.get(stg)
                            new_stg = CrmFunnelStage()
                            new_stg.id_funnel  = fun.id
                            setattr(new_stg,"name",('' if cfg_stg is None else cfg_stg.name))
                            setattr(new_stg,"icon",('' if cfg_stg is None else cfg_stg.icon))
                            setattr(new_stg,"icon_color",('' if cfg_stg is None else cfg_stg.icon_color))
                            setattr(new_stg,"color",(cfg_stg.color if cfg_stg is not None else None))
                            setattr(new_stg,"order",(cfg_stg.order if cfg_stg is not None else None))
                            db.session.add(new_stg)
                        db.session.commit()
            return True
            
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_calendar.response(HTTPStatus.OK,"Exclui os dados de um evento")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self,id:int):
        pass

class CalendarEventList(Resource):
    @ns_calendar.response(HTTPStatus.OK,"Obtem a listagem de eventos do calendario (baseado em data de inicio e fim)")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @ns_calendar.param("query","Texto para busca de intervalos de datas e eventos","query")
    @auth.login_required
    def get(self):
        query   = "" if request.args.get("query") is None else request.args.get("query")

        try:
            params = _get_params(query)
            if params is None:
                return None
            if params.start=="" and params.end=="":
                params.start = date(datetime.now().year,1,1)
                params.end   = date(datetime.now().year,12,31)

            yquery = Select(ScmEvent.id,
                            ScmEvent.id_parent,
                            ScmEvent.name,
                            ScmEvent.year,
                            ScmEvent.start_date,
                            ScmEvent.end_date,
                            ScmEvent.budget_value,
                            ScmEvent.date_created,
                            ScmEvent.date_updated,
                            ScmEventType.id.label("id_event_type"),
                            ScmEventType.name.label("event_type_name"),
                            ScmEventType.hex_color,
                            ScmEventType.has_budget,
                            ScmEventType.is_milestone,
                            B2bCollection.id.label("id_collection"),
                            B2bCollection.name.label("collection_name"),
                            B2bBrand.id.label("id_brand"),
                            B2bBrand.name.label("brand_name")).distinct()\
                .join(ScmEventType,ScmEventType.id==ScmEvent.id_event_type)\
                .join(ScmCalendar,and_(ScmEvent.year==ScmCalendar.year,ScmEvent.start_date==ScmCalendar.calendar_date))\
                .outerjoin(B2bCollection,ScmEvent.id_collection==B2bCollection.id)\
                .outerjoin(B2bBrand,B2bCollection.id_brand==B2bBrand.id)\
                .where(between(ScmCalendar.calendar_date,params.start,params.end))\
                .where(or_(ScmEvent.id_parent.is_(None),ScmEvent.id_parent==0))\
                .order_by(asc(ScmEvent.start_date))
            
            if hasattr(params,'entity_type'):
                yquery = yquery.where(ScmEventType.id==int(params.entity_type))

            retorno = [{
                    "id": e.id,
                    "id_parent": e.id_parent,
                    "name": e.name,
                    "start_week": date(e.start_date.year,e.start_date.month,e.start_date.day).isocalendar().week,
                    "end_week": date(e.end_date.year,e.end_date.month,e.end_date.day).isocalendar().week,
                    "start_date": e.start_date.strftime("%Y-%m-%d"),
                    "end_date": e.end_date.strftime("%Y-%m-%d"),
                    "year":e.year,
                    "budget_value": None if e.budget_value is None else json.dumps(e.budget_value),
                    "date_created": e.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_updated": e.date_updated.strftime("%Y-%m-%d %H:%M:%S") if e.date_updated is not None else None,
                    "type": {
                        "id": e.id_event_type,
                        "name": e.event_type_name,
                        "hex_color": e.hex_color,
                        "has_budget": e.has_budget,
                        "is_milestone": e.is_milestone
                    },
                    "collection":{
                        "id":e.id_collection,
                        "name": e.collection_name,
                        "brand":{
                            "id": e.id_brand,
                            "name": e.brand_name
                        }
                    },
                    "children": get_children(e.id)
                } for e in db.session.execute(yquery).all()]

            return retorno
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

ns_calendar.add_resource(CalendarEventList,"/all-events")


class EventList(Resource):
    @ns_calendar.response(HTTPStatus.OK,"Obtem a listagem de eventos do sistema")
    @ns_calendar.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_calendar.param("page","Número da página de registros","query",type=int,required=True)
    @ns_calendar.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_calendar.param("query","Texto para busca","query")
    def get(self):
        pag_num  = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query    = "" if request.args.get("query") is None else str(request.args.get("query"))
        try:
            params    = _get_params(query)
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc
            order_by  = 'id' if not hasattr(params,'order_by') else params.order_by if params is not None else 'id'
            search    = None if not hasattr(params,"search") else params.search if params is not None else None
            trash     = False if not hasattr(params,'trash') else True
            list_all  = False if not hasattr(params,'list_all') else True

            just_parent = False if not hasattr(params,'just_parent') else True

            rquery = Select(ScmEvent.id,
                            ScmEvent.id_parent,
                            ScmEvent.name,
                            ScmEvent.year,
                            ScmEvent.start_date,
                            ScmEvent.end_date,
                            ScmEvent.budget_value,
                            ScmEvent.date_created,
                            ScmEvent.date_updated,
                            ScmEventType.id.label("id_event_type"),
                            ScmEventType.name.label("event_type_name"),
                            ScmEventType.hex_color,
                            ScmEventType.has_budget,
                            ScmEventType.is_milestone,
                            B2bCollection.id.label("id_collection"),
                            B2bCollection.name.label("collection_name"),
                            B2bBrand.id.label("id_brand"),
                            B2bBrand.name.label("brand_name")).distinct()\
                .join(ScmEventType,ScmEventType.id==ScmEvent.id_event_type)\
                .join(ScmCalendar,and_(ScmEvent.year==ScmCalendar.year,ScmEvent.start_date==ScmCalendar.calendar_date))\
                .outerjoin(B2bCollection,ScmEvent.id_collection==B2bCollection.id)\
                .outerjoin(B2bBrand,B2bCollection.id_brand==B2bBrand.id)\
                .where(ScmEvent.trash==trash)\
                .where(ScmEventType.is_milestone==False)\
                .order_by(direction(getattr(ScmEvent,order_by)))
            
            if just_parent == True:
                rquery = rquery.where(or_(ScmEvent.id_parent.is_(None),ScmEvent.id_parent==0))
            
            if search is not None:
                rquery = rquery.where(ScmEvent.name.like("%{}%".format(search)))

            if not list_all:
                pag = db.paginate(rquery,page=pag_num,per_page=pag_size)
                rquery = rquery.limit(pag_size).offset((pag_num - 1) * pag_size)

                retorno = {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next
                    },
                    "data":[{
                        "id": m.id,
                        "id_parent": m.id_parent,
                        "name": m.name,
                        "year": m.year,
                        "start_date": m.start_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_date": m.end_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "budged_value": simplejson.dumps(Decimal(0 if m.budget_value is None else m.budget_value)),
                        "type": {
                            "id": m.id_event_type,
                            "name": m.event_type_name,
                            "hex_color": m.hex_color,
                            "has_budget": m.has_budget,
                            "is_milestone": m.is_milestone
                        },
                        "collection":{
                            "id":m.id_collection,
                            "name": m.collection_name,
                            "brand":{
                                "id": m.id_brand,
                                "name": m.brand_name
                            }
                        },
                        "children": get_children(m.id),
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
                }
            else:
                retorno = [{
                        "id": m.id,
                        "id_parent": m.id_parent,
                        "name": m.name,
                        "year": m.year,
                        "start_date": m.start_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_date": m.end_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "budged_value": simplejson.dumps(Decimal(0 if m.budget_value is None else m.budget_value)),
                        "type": {
                            "id": m.id_event_type,
                            "name": m.event_type_name,
                            "hex_color": m.hex_color,
                            "has_budget": m.has_budget,
                            "is_milestone": m.is_milestone
                        },
                        "collection":{
                            "id": m.id_collection,
                            "name": m.collection_name,
                            "brand":{
                                "id": m.id_brand,
                                "name": m.brand_name
                            }
                        },
                        "children": get_children(m.id),
                        "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                        "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                    } for m in db.session.execute(rquery)]
            return retorno
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

ns_calendar.add_resource(EventList,"/events")