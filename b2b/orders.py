import calendar
import requests
import importlib
import simplejson
from auth import auth
from os import environ
from flask import request
from http import HTTPStatus
from decimal import Decimal
from datetime import datetime
from common import _extract_token
from models.helpers import _get_params, db
from flask_restx import Resource,Namespace,fields
from f2bconfig import EntityAction, DevolutionStatus, OrderStatus
from sqlalchemy import Update, and_, exc, Select, Delete, asc, desc, func
from models.tenant import CmmTranslateSizes, FprDevolution, _save_entity_log
from models.tenant import B2bCartShopping, B2bOrders,B2bOrdersProducts, B2bPaymentConditions, CmmLegalEntities
from models.tenant import B2bCustomerGroup, B2bCustomerGroupCustomers, B2bProductStock, B2bTarget, CmmProducts, CmmTranslateColors

ns_order = Namespace("orders",description="Operações para manipular dados de pedidos")

prd_pag_model = ns_order.model(
    "Pagination",{
        "registers": fields.Integer,
        "page": fields.Integer,
        "per_page": fields.Integer,
        "pages": fields.Integer,
        "has_next": fields.Boolean
    }
)

prd_ord_model = ns_order.model(
    "ProductsOrder",{
        "id_product": fields.Integer,
        "color": fields.String,
        "size" : fields.String,
        "quantity": fields.Integer,
        "price": fields.Float,
        "discount": fields.Float,
        "discount_percentage": fields.Float
    }
)

ord_model = ns_order.model(
    "Order",{
        "id": fields.String,
        "id_customer": fields.Integer,
        "id_payment_condition": fields.Integer,
        "date_created": fields.DateTime,
        "date_updated": fields.DateTime,
        "products": fields.List(fields.Nested(prd_ord_model))
    }
)

ord_return = ns_order.model(
    "OrderReturn",{
        "pagination": fields.Nested(prd_pag_model),
        "data": fields.List(fields.Nested(ord_model))
    }
)


####################################################################################
#                  INICIO DAS CLASSES QUE IRAO TRATAR OS  PEDIDOS.                 #
####################################################################################
@ns_order.route("/")
class OrdersList(Resource):
    @ns_order.response(HTTPStatus.OK,"Obtem a listagem de pedidos",ord_return)
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @ns_order.param("page","Número da página de registros","query",type=int,required=True)
    @ns_order.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_order.param("query","Texto para busca","query")
    @auth.login_required
    def get(self):
        pag_num  =  1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query   = "" if request.args.get("query") is None else request.args.get("query")

        try:
            params    = _get_params(str(query))
            # direction = asc if not hasattr(params,'order') else asc if str(params.order).upper()=='ASC' else desc
            # order_by  = 'id' if not hasattr(params,'order_by') else params.order_by
            search    = None if not hasattr(params,"search") else params.search if params is not None else None
            # trash     = True if not hasattr(params,'active') else False #foi invertido
            # list_all  = False if not hasattr(params,'list_all') else True


            if search is not None:

                #pensar nos filtros para essa listagem
                rquery = B2bOrders.query.paginate(page=pag_num,per_page=pag_size)
            else:
                rquery = B2bOrders.query.filter(B2bOrders.trash.is_(False)).paginate(page=pag_num,per_page=pag_size)

            return {
                "pagination":{
                    "registers": rquery.total,
                    "page": pag_num,
                    "per_page": pag_size,
                    "pages": rquery.pages,
                    "has_next": rquery.has_next
                },
                "data":[{
                    "id": m.id,
                    "id_customer": m.id_customer,
                    "make_online": m.make_online,
                    "id_payment_condition": m.id_payment_condition,
                    "date_created": m.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_updated": m.date_updated.strftime("%Y-%m-%d %H:%M:%S") if m.date_updated is not None else None
                } for m in rquery.items]
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    @ns_order.response(HTTPStatus.OK,"Cria um novo pedido")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao criar pedido!")
    @ns_order.doc(body=ord_model)
    @auth.login_required
    def post(self)->int|dict:
        try:
            req = request.get_json()

            for customer in req['customers']:

                # verificar pelo tipo do cliente se precisa ou nao aprovacao de pedidos
                cst = db.session.execute(
                    Select(B2bCustomerGroup.need_approvement).select_from(B2bCustomerGroup)\
                    .join(B2bCustomerGroupCustomers,B2bCustomerGroup.id==B2bCustomerGroupCustomers.id_customer_group)\
                    .where(B2bCustomerGroupCustomers.id_customer==customer)
                ).first()

                # tira-se por base que a necessidade de aprovacao eh usada
                # quando o cliente estiver associado a um representante e 
                # indicado no cadastro dos grupos de clientes, caso contrario
                # nao precisarah de aprovacao
                need_approvement = False
                if cst is not None:
                    need_approvement = cst.need_approvement

                order = B2bOrders()
                order.id_customer          = customer
                #order.make_online         = req['make_online']
                setattr(order,"id_payment_condition",int(req['id_payment_condition']))
                order.installment_value    = req['installment_value']
                order.installments         = req['installments']
                setattr(order,"date",datetime.now())

                # se o usuario for lojista faz o status conforme a necessidade de aprovacao
                # caso contrario o pedido entra como processando
                if req["user_type"]=='L' or req["user_type"]=='I':
                    setattr(order,"status",(OrderStatus.ANALIZING.value if need_approvement == 1 else OrderStatus.PROCESSING.value))
                else:
                    setattr(order,"status",OrderStatus.PROCESSING.value)
                order.total_value          = req['total_value']
                order.total_itens          = req['total_itens']
                setattr(order,"trash",False)
                db.session.add(order)
                db.session.commit()

                stmt = Select(B2bCartShopping).where(B2bCartShopping.id_customer==customer)

                for cart in db.session.execute(stmt).scalars():
                    prod = B2bOrdersProducts()
                    prod.id_order   = order.id
                    prod.id_product = cart.id_product
                    prod.id_color   = cart.id_color
                    prod.id_size    = cart.id_size
                    prod.price      = cart.price
                    prod.quantity   = cart.quantity
                    setattr(prod,"discount",0)
                    setattr(prod,"discount_percentage",0)
                    db.session.add(prod)
                
                db.session.commit()

                #apaga o conteudo do carrinho de compras que nao se faz mais necessario
                stmt = Delete(B2bCartShopping).where(B2bCartShopping.id_customer==customer)
                db.session.execute(stmt)
                db.session.commit()

                _save_entity_log(customer,EntityAction.ORDER_CREATED,'Novo pedido realizado ('+str('{:010d}'.format(order.id))+') - em '+datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


@ns_order.route("/<int:id>")
@ns_order.param("id","Id do registro")
class OrderApi(Resource):
    @ns_order.response(HTTPStatus.OK,"Obtem um registro de pedido",ord_model)
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def get(self,id:int):
        try:
            order = db.session.execute(Select(B2bOrders.total_value,
                           B2bOrders.total_itens,
                           B2bOrders.installments,
                           B2bOrders.installment_value,
                           B2bOrders.status,
                           B2bOrders.integration_number,
                           B2bOrders.track_code,
                           B2bOrders.track_company,
                           B2bOrders.invoice_number,
                           B2bOrders.invoice_serie,
                           B2bOrders.date_created,
                           B2bOrders.date_updated,
                           B2bOrders.date,
                           CmmLegalEntities.fantasy_name,
                           B2bOrders.id_customer,
                           B2bOrders.id_payment_condition,
                           B2bPaymentConditions.name.label("payment_condition")
                           )\
                        .join(CmmLegalEntities,CmmLegalEntities.id==B2bOrders.id_customer)\
                        .join(B2bPaymentConditions,B2bPaymentConditions.id==B2bOrders.id_payment_condition)\
                        .where(B2bOrders.id==id)).first()
            iquery = Select(B2bOrdersProducts.id_product,
                            CmmProducts.name,
                            CmmProducts.refCode,
                            B2bOrdersProducts.id_color,
                            CmmTranslateColors.name.label("color"),
                            B2bOrdersProducts.id_size,
                            CmmTranslateSizes.new_size.label("size"),
                            B2bOrdersProducts.quantity,
                            B2bOrdersProducts.price,
                            B2bOrdersProducts.discount,
                            B2bOrdersProducts.discount_percentage,
                            B2bProductStock.in_order,
                            B2bProductStock.quantity.label("stock"),
                            B2bProductStock.ilimited)\
                        .join(CmmProducts,CmmProducts.id==B2bOrdersProducts.id_product)\
                        .join(CmmTranslateColors,CmmTranslateColors.id==B2bOrdersProducts.id_color)\
                        .join(CmmTranslateSizes,CmmTranslateSizes.id==B2bOrdersProducts.id_size)\
                        .join(B2bProductStock,and_(
                            B2bProductStock.id_product==CmmProducts.id,
                            B2bProductStock.id_color==B2bOrdersProducts.id_color,
                            B2bProductStock.id_size==B2bOrdersProducts.id_size
                        ))\
                        .where(B2bOrdersProducts.id_order==id)
            if order is None:
                return {
                    "error_code": HTTPStatus.BAD_REQUEST.value,
                    "error_details": "Registro não encontrado!",
                    "error_sql": ""
                }, HTTPStatus.BAD_REQUEST
            
            return {
                "id": id,
                "customer": {
                    "id": order.id_customer,
                    "name": order.fantasy_name,
                },
                "payment_condition": {
                    "id": order.id_payment_condition,
                    "name": order.payment_condition
                },
                "total_value": str(order.total_value),
                "total_itens": str(order.total_itens),
                "installments": str(order.installments),
                "installments_value": str(order.installment_value),
                "date": order.date.strftime("%Y-%m-%d"),
                "status": order.status,
                "integration_number": None if order.integration_number is None else str(order.integration_number),
                "track_code": None if order.track_code is None else order.track_code,
                "track_company": None if order.track_company is None else order.track_company,
                "invoice_number": None if order.invoice_number is None else str(order.invoice_number),
                "invoice_serie": None if order.invoice_serie is None else str(order.invoice_serie),
                "date_created": order.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "date_updated": None if order.date_updated is None else order.date_updated.strftime("%Y-%m-%d %H:%M:%S"),
                "products": [{
                    "id_order_product": str(m.id_product)+'_'+str(m.id_color)+'_'+str(m.id_size),
                    "id_product": m.id_product,
                    "refCode": m.refCode,
                    "name": m.name,
                    "id_color": m.id_color,
                    "color": m.color,
                    "id_size": m.id_size,
                    "size" : m.size,
                    "quantity": str(m.quantity),
                    "price": str(m.price),
                    "discount": str(m.discount),
                    "discount_percentage": str(m.discount_percentage),
                    "stock_quantity": "999+" if m.ilimited==1 else (m.stock-m.in_order)
                }for m in db.session.execute(iquery)]
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


    @ns_order.response(HTTPStatus.OK,"Atualiza os dados de um pedido")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @ns_order.doc(body=ord_model)
    @auth.login_required
    def post(self,id:int)->bool|dict:
        try:
            req = request.get_json()

            ord_prod = db.session.execute(
                Select(
                    B2bOrdersProducts.id_order,
                    B2bOrdersProducts.id_product,
                    B2bOrdersProducts.id_color,
                    B2bOrdersProducts.id_size,
                    B2bOrdersProducts.quantity,
                    B2bOrdersProducts.price,
                    B2bOrdersProducts.discount,
                    B2bOrdersProducts.discount_percentage).where(B2bOrdersProducts.id_order==id)
            )

            total_value = 0
            total_itens = 0
            for prod in req["products"]:
                total_value += (float(prod["price"])*int(prod["quantity"]))
                total_itens += int(prod["quantity"])
                # exclui se a quantidade estiver zerada
                if prod["quantity"]==0:
                    db.session.execute(Delete(B2bOrdersProducts).where(
                        and_(
                            B2bOrdersProducts.id_order==id,
                            B2bOrdersProducts.id_product==prod["id_product"],
                            B2bOrdersProducts.id_color==prod["id_color"],
                            B2bOrdersProducts.id_size==prod["id_size"]
                        )
                    ))
                    db.session.commit()
                else:
                    for op in ord_prod:
                        # se a quantidade mudou, entao atualiza a quantidade
                        if op.id_order==id and\
                            op.id_product==prod["id_product"] and\
                            op.id_color==prod["id_color"] and\
                            op.id_size==prod["id_size"] and op.quantity!=int(prod["quantity"]):
                            db.session.execute(
                                Update(B2bOrdersProducts).values(quantity=int(prod["quantity"]))\
                                .where(and_(
                                    B2bOrdersProducts.id_order==id,
                                    B2bOrdersProducts.id_product==prod["id_product"],
                                    B2bOrdersProducts.id_color==prod["id_color"],
                                    B2bOrdersProducts.id_size==prod["id_size"]
                                ))
                            )
                            db.session.commit()
            
            #atualiza as informacoes de cabecalho do produto
            order:B2bOrders = B2bOrders.query.get(id) # type: ignore
            setattr(order,"total_itens",total_itens)
            setattr(order,"total_value",total_value)
            setattr(order,"installment_value",(total_value/order.installments))
            order.status = req["status"]
            db.session.commit()

            _save_entity_log(
                order.id_customer, # type: ignore
                EntityAction.ORDER_DELETED if req["status"]==OrderStatus.REJECTED else EntityAction.ORDER_UPDATED,
                'Pedido '+('excluído' if req["status"]==OrderStatus.REJECTED else 'atualizado')+' ('+str('{:010d}'.format(order.id))+') - em '+datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_order.response(HTTPStatus.OK,"Exclui os dados de um pedido")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Registro não encontrado!")
    @auth.login_required
    def delete(self,id:int):
        try:
            req   = request.get_json()
            order:B2bOrders|None = B2bOrders.query.get(id)
            setattr(order,"trash",True)
            db.session.commit()
            if (req["id_customer"]!=0):
                _save_entity_log(req['id_customer'],EntityAction.ORDER_DELETED,'Pedido ('+str(id)+') cancelado pelo cliente em '+datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            else:
                legal:CmmLegalEntities = CmmLegalEntities.query.get(req["id_representative"]) # type: ignore
                _save_entity_log(
                    order.id_customer, # type: ignore
                    EntityAction.ORDER_DELETED,
                    'Pedido ('+str(id)+') cancelado pelo representante ('+str(legal.name)+') em '+datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    )
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }


class HistoryOrderList(Resource):
    @ns_order.response(HTTPStatus.OK,"Obtem a listagem de produtos de pedidos",[prd_ord_model])
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @ns_order.param("page","Número da página de registros","query",type=int,required=True)
    @ns_order.param("pageSize","Número de registros por página","query",type=int,required=True,default=25)
    @ns_order.param("query","Texto para busca","query")
    @auth.login_required
    def get(self):
        pag_num   = 1 if request.args.get("page") is None else int(str(request.args.get("page")))
        pag_size  = int(str(environ.get("F2B_PAGINATION_SIZE"))) if request.args.get("pageSize") is None else int(str(request.args.get("pageSize")))
        query     = "" if request.args.get("query") is None else request.args.get("query")
        try:
            params = _get_params(str(query))
            order_by  = "id" if not hasattr(params,"order_by") else params.order_by if params is not None else 'id'
            direction = asc if not hasattr(params,'order') else asc if params is not None and params.order=='ASC' else desc
            list_all  = False if not hasattr(params,"list_all") else True
            status    = None if not hasattr(params,"status") else params.status if params is not None else params
            no_devolution = False if not hasattr(params,"no_devolution") else True

            stmt = Select(
                          B2bOrders.id.label("id_order"),
                          B2bOrders.date_created,
                          B2bOrders.installment_value,
                          B2bOrders.installments,
                          B2bOrders.total_value,
                          B2bOrders.total_itens,
                          B2bOrders.status,
                          B2bOrders.integration_number,
                          B2bOrders.track_code,
                          B2bOrders.track_company,
                          B2bOrders.invoice_number,
                          B2bOrders.invoice_serie,
                          B2bOrders.id_customer,
                          CmmLegalEntities.name.label("customer_name"),
                          CmmLegalEntities.taxvat,
                          B2bOrders.id_payment_condition,
                          B2bPaymentConditions.name.label("payment_name"))\
                .join(B2bPaymentConditions,B2bPaymentConditions.id==B2bOrders.id_payment_condition)\
                .join(CmmLegalEntities,CmmLegalEntities.id==B2bOrders.id_customer)\
                .order_by(direction(getattr(B2bOrders, order_by)))
            
            # if "Authorization" in request.headers:
            #     tkn = request.headers["Authorization"].replace("Bearer ","")
            #     if tkn is not None:
            #         token = _extract_token(tkn)

            #         access = db.session.execute(
            #             Select(CmmUsers.type)\
            #             .join(CmmUserEntity,CmmUserEntity.id_user==CmmUsers.id)\
            #             .where(CmmUserEntity.id_entity==id)
            #         ).first()
            #         if access is not None:
            #             if access.type!='A' and access.type!='L':
            #                 stmt = stmt.where(B2bOrders.id_customer==id)

            if status is not None:
                stmt = stmt.where(B2bOrders.status==status)

            if no_devolution is True:
                stmt = stmt.where(B2bOrders.id.not_in(
                    Select(FprDevolution.id_order).where(FprDevolution.status!=DevolutionStatus.REJECTED.value)
                ))
                    
            track_order = False
            url =str(environ.get("F2B_SMC_URL"))+"/config/"+str(request.headers.get("x-customer"))
            cfg_req = requests.get(url)
            if cfg_req.status_code==HTTPStatus.OK.value:
                cfg = cfg_req.json()
                track_order = bool(cfg["track_orders"])

            # _show_query(stmt)
            
            if not list_all:
                pag = db.paginate(stmt,page=pag_num,per_page=pag_size)
                stmt = stmt.limit(pag_size).offset((pag_num - 1) * pag_size)

                return {
                    "pagination":{
                        "registers": pag.total,
                        "page": pag_num,
                        "per_page": pag_size,
                        "pages": pag.pages,
                        "has_next": pag.has_next
                    },
                    "data": [{
                        "id_order": '{:010d}'.format(r.id_order),
                        "id_order_number": r.id_order,
                        "id_customer": r.id_customer,
                        "customer_name": r.customer_name,
                        "id_payment_condition": r.id_payment_condition,
                        "payment_name": r.payment_name,
                        "total_value": simplejson.dumps(Decimal(r.total_value)),
                        "total_itens": r.total_itens,
                        "installments": r.installments,
                        "installment_value": simplejson.dumps(Decimal(r.installment_value)),
                        "status": r.status,
                        "integration_number": r.integration_number,
                        "invoice_number": r.invoice_number,
                        "track": (None if track_order is False else self.__getTrack(
                            r.taxvat,
                            r.invoice_number,
                            r.invoice_serie,
                            r.track_company,
                            r.track_code,
                            cfg.id_customer) ),
                        "date_created": r.date_created.strftime("%d/%m/%Y %H:%M:%S")
                    }for r in db.session.execute(stmt)]
                }
            else:
                return [{
                        "id_order": '{:010d}'.format(r.id_order),
                        "id_order_number": r.id_order,
                        "id_customer": r.id_customer,
                        "customer_name": r.customer_name,
                        "id_payment_condition": r.id_payment_condition,
                        "payment_name": r.payment_name,
                        "total_value": simplejson.dumps(Decimal(r.total_value)),
                        "total_itens": r.total_itens,
                        "installments": r.installments,
                        "installment_value": simplejson.dumps(Decimal(r.installment_value)),
                        "status": r.status,
                        "integration_number": r.integration_number,
                        "invoice_number": r.invoice_number,
                        "track": (None if track_order is False else self.__getTrack(
                            r.taxvat,
                            r.invoice_number,
                            r.invoice_serie,
                            r.track_company,
                            r.track_code,
                            cfg.id_customer) ),
                        "date_created": r.date_created.strftime("%d/%m/%Y %H:%M:%S")
                    }for r in db.session.execute(stmt)]
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    def __getTrack(self,_cnpj:str,_nf:int,_nf_serie:int,_emp:str,_code:str,_tenant:str):

        class_name = str(_emp).lower().replace("_","").title().replace(" ","")
        SHIPPING = getattr(
            importlib.import_module('integrations.shipping.'+str(_emp).lower()),
            class_name
        )

        track = SHIPPING()

        return track.tracking(_cnpj,_nf,_nf_serie,_tenant=_tenant)
        
ns_order.add_resource(HistoryOrderList,'/history/')


class HistoryOrderApi(Resource):
    @ns_order.response(HTTPStatus.OK,"Obtem o total de pedidos realizados com base na meta")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @auth.login_required
    def get(self):
        try:
            date_start = str(datetime.now().year)+'-01-01'
            date_end   = str(datetime.now().year)+'-12-31'

            target_type = db.session.execute(Select(B2bTarget.type).where(B2bTarget.year==datetime.now().year)).one().type
            if target_type=='Q':
                if datetime.now().month>=1 and datetime.now().month<=3:
                    date_start = str(datetime.now().year)+'-01-01'
                    date_end   = str(datetime.now().year)+'-03-'+str(calendar.monthrange(datetime.now().year,3)[1])
                elif datetime.now().month>=4 and datetime.now().month<=6:
                    date_start = str(datetime.now().year)+'-04-01'
                    date_end   = str(datetime.now().year)+'-06-'+str(calendar.monthrange(datetime.now().year,6)[1])
                elif datetime.now().month>=7 and datetime.now().month<=9:
                    date_start = str(datetime.now().year)+'-07-01'
                    date_end   = str(datetime.now().year)+'-09-'+str(calendar.monthrange(datetime.now().year,9)[1])
                else:
                    date_start = str(datetime.now().year)+'-10-01'
                    date_end   = str(datetime.now().year)+'-12-'+str(calendar.monthrange(datetime.now().year,12)[1])
            else:
                date_start = str(datetime.now().year)+'-'+str(datetime.now().month)+'-01'
                date_end   = str(datetime.now().year)+'-'+str(datetime.now().month)+'-'+str(calendar.monthrange(datetime.now().year,datetime.now().month)[1])

            stmt = Select(func.count(B2bOrders.id).label('total'))\
                .where(
                    and_(
                        B2bOrders.status==OrderStatus.FINISHED.value,
                        B2bOrders.date.between(date_start,date_end)
                    )
                )
            
            result = db.session.execute(stmt).first()
            total  = 0 if result is None or result.total is None else result.total
            return total
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_order.response(HTTPStatus.OK,"Obtem o valor total de pedidos realizados com base na meta")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    @auth.login_required
    def post(self):
        try:
            date_start = str(datetime.now().year)+'-01-01'
            date_end   = str(datetime.now().year)+'-12-31'

            target_type = db.session.execute(Select(B2bTarget.type).where(B2bTarget.year==datetime.now().year)).one().type
            if target_type=='Q':
                if datetime.now().month>=1 and datetime.now().month<=3:
                    date_start = str(datetime.now().year)+'-01-01'
                    date_end   = str(datetime.now().year)+'-03-'+str(calendar.monthrange(datetime.now().year,3)[1])
                elif datetime.now().month>=4 and datetime.now().month<=6:
                    date_start = str(datetime.now().year)+'-04-01'
                    date_end   = str(datetime.now().year)+'-06-'+str(calendar.monthrange(datetime.now().year,6)[1])
                elif datetime.now().month>=7 and datetime.now().month<=9:
                    date_start = str(datetime.now().year)+'-07-01'
                    date_end   = str(datetime.now().year)+'-09-'+str(calendar.monthrange(datetime.now().year,9)[1])
                else:
                    date_start = str(datetime.now().year)+'-10-01'
                    date_end   = str(datetime.now().year)+'-12-'+str(calendar.monthrange(datetime.now().year,12)[1])
            else:
                date_start = str(datetime.now().year)+'-'+str(datetime.now().month)+'-01'
                date_end   = str(datetime.now().year)+'-'+str(datetime.now().month)+'-'+str(calendar.monthrange(datetime.now().year,datetime.now().month)[1])

            stmt = Select(func.sum(B2bOrders.total_value).label('total'))\
                .where(
                    and_(
                        B2bOrders.status==OrderStatus.FINISHED.value,
                        B2bOrders.date.between(date_start,date_end)
                    )
                )
            result = db.session.execute(stmt).first()
            total  = 0 if result is None or result.total is None else result.total

            return total
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }
    
    @ns_order.response(HTTPStatus.OK,"Obtem o valor por representante de pedidos realizados com base na meta")
    @ns_order.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros!")
    def put(self):
        try:
            date_start = str(datetime.now().year)+'-01-01'
            date_end   = str(datetime.now().year)+'-12-31'

            target_type = db.session.execute(Select(B2bTarget.type).where(B2bTarget.year==datetime.now().year)).one().type
            if target_type=='Q':
                if datetime.now().month>=1 and datetime.now().month<=3:
                    date_start = str(datetime.now().year)+'-01-01'
                    date_end   = str(datetime.now().year)+'-03-'+str(calendar.monthrange(datetime.now().year,3)[1])
                elif datetime.now().month>=4 and datetime.now().month<=6:
                    date_start = str(datetime.now().year)+'-04-01'
                    date_end   = str(datetime.now().year)+'-06-'+str(calendar.monthrange(datetime.now().year,6)[1])
                elif datetime.now().month>=7 and datetime.now().month<=9:
                    date_start = str(datetime.now().year)+'-07-01'
                    date_end   = str(datetime.now().year)+'-09-'+str(calendar.monthrange(datetime.now().year,9)[1])
                else:
                    date_start = str(datetime.now().year)+'-10-01'
                    date_end   = str(datetime.now().year)+'-12-'+str(calendar.monthrange(datetime.now().year,12)[1])
            else:
                date_start = str(datetime.now().year)+'-'+str(datetime.now().month)+'-01'
                date_end   = str(datetime.now().year)+'-'+str(datetime.now().month)+'-'+str(calendar.monthrange(datetime.now().year,datetime.now().month)[1])
            
            stmt = Select(
                func.coalesce(CmmLegalEntities.fantasy_name,'SEM REPRESENTACAO').label("fantasy_name"),
                func.sum(B2bOrders.total_value).label("total")).select_from(B2bOrders)\
                .outerjoin(B2bCustomerGroupCustomers,B2bCustomerGroupCustomers.id_customer==B2bOrders.id_customer)\
                .outerjoin(B2bCustomerGroup,B2bCustomerGroup.id==B2bCustomerGroupCustomers.id_customer_group)\
                .outerjoin(CmmLegalEntities,CmmLegalEntities.id==B2bCustomerGroup.id_representative)\
                .where(
                    and_(
                        B2bOrders.status==OrderStatus.FINISHED.value,
                        B2bOrders.date.between(date_start,date_end)
                    )
                )\
                .group_by(CmmLegalEntities.fantasy_name)
            return {
                "representative":[r.fantasy_name for r in db.session.execute(stmt)],
                "total": ["{:10.2f}".format(r.total) for r in db.session.execute(stmt)]
                #"total": "{:10.2f}".format(r.total) if r.total is not None else 0,
            }
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

        
ns_order.add_resource(HistoryOrderApi,'/total/')