
from auth import auth
from flask import request
from http import HTTPStatus
from models.helpers import db
from flask_restx import Resource,Namespace,fields
from models.tenant import B2bCartShopping, B2bCustomerGroup
from models.tenant import CmmTranslateSizes,CmmProductsImages
from models.tenant import B2bCustomerGroupCustomers, B2bProductStock
from models.tenant import CmmLegalEntities, CmmProducts, CmmProductsGrid
from models.tenant import CmmProductsGridDistribution, CmmTranslateColors
from sqlalchemy import exc, Select, and_, func, tuple_, distinct, desc, asc, Delete, text

ns_cart = Namespace("cart",description="Operações para manipular dados do carrinho de compras")

m_list_content = ns_cart.model(
    "Content",{
        "customer":fields.Integer,
        "color": fields.Integer,
        "products": fields.List(fields.Integer)
    }
)

@ns_cart.route("/")
class CartApi(Resource):
    @ns_cart.response(HTTPStatus.OK,"Retorna os dados de produtos que estão no carrinho de compras")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao listar registros")
    @ns_cart.param("id_profile","Número da página de registros","query",type=int,required=True,default=1)
    @ns_cart.param("order_by","Campo de ordenacao","query")
    @ns_cart.param("order_dir","Direção da ordenação","query",enum=['ASC','DESC'])
    @auth.login_required
    def get(self):
        id_profile =  int(str(request.args.get("id_profile")))
        order_by   = "id_product" if request.args.get("order_by") is None else request.args.get("order_by")
        direction  = desc if request.args.get("order_dir") == 'DESC' else asc
        user_type  = request.args.get("userType")

        try:
            
            pquery = Select(B2bCartShopping.id_product,
                            B2bCartShopping.id_customer,
                            CmmLegalEntities.fantasy_name,
                            func.sum(B2bCartShopping.price).label("price"),
                            CmmProductsImages.img_url,
                            CmmProducts.name,
                            CmmProducts.refCode,
                            func.sum(B2bCartShopping.quantity).label("total")).distinct()\
                .join(CmmProductsImages,and_(CmmProductsImages.id_product==B2bCartShopping.id_product,CmmProductsImages.img_default.is_(True)))\
                .join(CmmLegalEntities,CmmLegalEntities.id==B2bCartShopping.id_customer)\
                .join(CmmProducts,CmmProducts.id==B2bCartShopping.id_product)\
                .group_by(
                    B2bCartShopping.id_product,
                    B2bCartShopping.id_customer,
                    CmmLegalEntities.fantasy_name,
                    CmmProducts.name,
                    CmmProducts.refCode,
                    CmmProductsImages.img_url).order_by(asc(B2bCartShopping.id_customer))
            
            #colors query
            cquery = Select(B2bCartShopping.id_color,
                            CmmTranslateColors.color,
                            CmmTranslateColors.hexcode,
                            CmmTranslateColors.name).distinct()\
                .join(CmmTranslateColors,CmmTranslateColors.id==B2bCartShopping.id_color)\
            
            if user_type=='C':
                pquery = pquery.where(B2bCartShopping.id_customer==id_profile)
            elif user_type=='R':
                pquery = pquery.where(B2bCartShopping.id_customer.in_(
                    Select(B2bCustomerGroupCustomers.id_customer)
                    .join(B2bCustomerGroup,B2bCustomerGroup.id==B2bCustomerGroupCustomers.id_customer_group)\
                    .where(B2bCustomerGroup.id_representative==id_profile)
                ))

            # _show_query(pquery)
            
            return [{
                "id_product": m.id_product,
                "id_customer":m.id_customer,
                "fantasy_name": m.fantasy_name,
                "ref": m.refCode,
                "name": m.name,
                "img_url": m.img_url,
                "price_un": float(str(m.price)),
                "itens": int(str(m.total)),
                "total_price": float(str(m.total*m.price)),
                "colors":[{
                    "id": c.id_color,
                    "name": c.name,
                    "hexa": c.hexcode,
                    "code": c.color,
                    "sizes":[{
                        "id": s.size_code,
                        "name": s.name,
                        "quantity": int(0 if s.quantity is None else s.quantity)
                    } for s in self.get_sizes(m.id_customer,m.id_product,c.id_color)]
                }for c in db.session.execute(cquery.where(and_(B2bCartShopping.id_customer==m.id_customer,B2bCartShopping.id_product==m.id_product)))]
            } for m in db.session.execute(pquery).all()]

        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "error_sql": e._sql_message()
            }

    def get_sizes(self,id_customer:int,id_product:int,color:int):
        query = Select(
                CmmTranslateSizes.new_size.label("size_code"),
                CmmTranslateSizes.id,
                CmmTranslateSizes.name,
                B2bCartShopping.quantity)\
                .select_from(B2bCartShopping)\
            .join(CmmProducts,CmmProducts.id==B2bCartShopping.id_product)\
            .join(CmmTranslateSizes,CmmTranslateSizes.id==B2bCartShopping.id_size)\
            .where(and_(
                B2bCartShopping.id_product==id_product,
                B2bCartShopping.id_color==color,
                B2bCartShopping.id_customer==id_customer
            ))
        # _show_query(query)

        return db.session.execute(query).all()

    @ns_cart.response(HTTPStatus.OK,"Retorna verdadeiro ou falso se conseguiu excluir o(s) registro(s)")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao excluir")
    @auth.login_required
    def delete(self):
        try:
            req = request.get_json()
            stmt = Delete(B2bCartShopping).where(
                and_(
                    B2bCartShopping.id_product.in_(req['products']),
                    B2bCartShopping.id_customer==int(req['customer'])
                )
            )
            db.session.execute(stmt)
            db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "errors_sql": e._sql_message()
            }

    @ns_cart.response(HTTPStatus.OK,"Salva os dados de produtos no carrinho de compras")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao salvar registro!")
    @auth.login_required
    def post(self):
        try:
            itens = request.get_json()

            for item in itens:
                #verifica se o produto jah estah no carrinho de compras
                pItem = db.session.execute(Select(B2bCartShopping).where(and_(
                    B2bCartShopping.id_customer==int(item['id_customer']),
                    B2bCartShopping.id_product==int(item['id_product']),
                    B2bCartShopping.id_color==item['id_color'],
                    B2bCartShopping.id_size==item['id_size']
                ))).scalar()
                if pItem is None:
                    it:B2bCartShopping = B2bCartShopping()
                    setattr(it,"id_customer",int(item['id_customer']))
                    setattr(it,"id_product",int(item['id_product']))
                    it.id_color    = item['id_color']
                    it.id_size     = item['id_size']
                    it.price       = item['price']
                    setattr(it,"quantity",int(item['quantity']))
                    it.user_create = item["user_create"]
                    db.session.add(it)
                    db.session.commit()
                else:
                    pItem.price       = item['price']
                    pItem.quantity    = int(item['quantity'])
                    pItem.user_update = item["user_create"]
                    db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "errors_sql": e._sql_message()
            }
    
    @ns_cart.response(HTTPStatus.OK,"Adição em massa de produtos no carrinho de compras utilizando a configuracao de grade")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao salvar registro!")
    @ns_cart.doc(body=m_list_content,description="Dados necessários dos produtos",name="content")
    def put(self):
        totalExecuted = 0
        try:
            req = request.get_json()
            
            for product in req['products']:
                #busca primeiramente a grade padrao dos produtos
                #se nao houver dados infelizmente nao restarah nada a ser feito
                gquery = db.session.execute(
                    Select(CmmProductsGridDistribution.id_size,
                                CmmProductsGridDistribution.value,CmmProducts.price)\
                        .join(CmmProductsGrid,CmmProductsGrid.id==CmmProductsGridDistribution.id_grid)\
                        .join(CmmProducts,CmmProducts.id_grid==CmmProductsGrid.id)\
                        .where(CmmProducts.id==product)
                    )

                if gquery is not None:
                    totalExecuted += 1
                    for size in gquery:
                        #realiza a busca da quantidade baseada nas informacoes da grade
                        squery = db.session.execute(
                            Select(B2bProductStock.quantity,B2bProductStock.id_color,B2bProductStock.ilimited,B2bProductStock.in_order)
                            .where(
                                and_(
                                    B2bProductStock.id_product == product,
                                    B2bProductStock.id_color.in_(req['colors']),
                                    B2bProductStock.id_size == size.id_size
                                )))
                        if squery is not None:
                            for stock in squery:
                                car_query = db.session.execute(Select(func.count().label("total")).select_from(B2bCartShopping).where(
                                    and_(
                                        B2bCartShopping.id_product==product,
                                        B2bCartShopping.id_color.in_(req['colors']),
                                        B2bCartShopping.id_size==size.id_size,
                                        B2bCartShopping.id_customer==req['customer']
                                    )
                                )).first()
                                if car_query is None or car_query.total == 0: # nao ha no carrinho
                                    # se o estoque for ilimitado ou disponivel adiciona ao carrinho
                                    if stock.ilimited is True or (stock.quantity-(0 if stock.in_order is  None else stock.in_order)) >= size.value:
                                        bcs = B2bCartShopping()
                                        bcs.id_product  = product
                                        bcs.id_customer = req['customer']
                                        bcs.id_color    = stock.id_color
                                        bcs.id_size     = size.id_size
                                        bcs.price       = size.price
                                        bcs.quantity    = size.value
                                        bcs.user_create = req['user']
                                        db.session.add(bcs)
                                        db.session.commit()
                                else: # estah no carrinho
                                    # se o estoque for ilimitado ou disponivel atualiza a informacao do carrinho
                                    if stock.ilimited is True or (stock.quantity-(0 if stock.in_order is None else stock.in_order)) >= size.value:
                                        bcs:B2bCartShopping = B2bCartShopping.query.get((req['customer'],product,stock.id_color,size.id_size)) # type: ignore
                                        bcs.quantity += size.value
                                        db.session.commit()
            return False if totalExecuted==0 else True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "errors_sql": e._sql_message()
            }


@ns_cart.route("/<int:id>")
@ns_cart.param("id","Id")
class CartItem(Resource):
    @ns_cart.hide
    @ns_cart.response(HTTPStatus.OK,"Metodo a ser implementado")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao salvar registro!")
    @auth.login_required
    def get(self,id:int):
        id_customer = int(str(request.args.get("id_profile")))
        cquery = Select(CmmTranslateColors.color,B2bCartShopping.id_color).distinct()\
            .join(CmmTranslateColors,CmmTranslateColors.id==B2bCartShopping.id_color)\
            .where(and_(B2bCartShopping.id_customer==id_customer,B2bCartShopping.id_product==id))
        
        squery = Select(CmmTranslateSizes.new_size.label("size"),B2bCartShopping.quantity).distinct()\
            .join(CmmTranslateSizes,CmmTranslateSizes.id==B2bCartShopping.id_size)\
            .where(and_(B2bCartShopping.id_product==id,B2bCartShopping.id_customer==id_customer))

        return {
            "id_product": id,
            "ref": "",
            "name": "",
            "img_url": "",
            "price_un": "",
            "total_price": "",
            "itens":0,
            "colors":[{
                "name": "",
                "hexa": "",
                "code": c.color,
                "sizes": [{
                    "name": s.size,
                    "quantity": int(s.quantity)
                }for s in db.session.execute(squery.where(B2bCartShopping.id_color==c.id_color))]
            }for c in db.session.execute(cquery)]
        }

    @ns_cart.response(HTTPStatus.OK,"Remove os itens do carrinho de compras")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao remover registros!")
    @auth.login_required
    def delete(self,id:int):
        try:
            usr_type = request.args.get("userType")
            if usr_type=='A':
                #no caso do administrador apagara pelo usuario de criacao do pedido
                #isso evitarah que apague pedidos de outros usuarios
                stmt = Delete(B2bCartShopping).where(B2bCartShopping.user_create==id)
            elif usr_type=='R':
                #quando representante apagara todos os clientes do representante
                stmt = Delete(B2bCartShopping).where(B2bCartShopping.id_customer.in_(
                    Select(B2bCustomerGroupCustomers.id_customer).where(B2bCustomerGroupCustomers.id_customer==id)
                    )
                )
            else:
                #sendo cliente apagarah somente os proprios pedidos
                stmt = Delete(B2bCartShopping).where(B2bCartShopping.id_customer==id)

            db.session.execute(stmt)
            db.session.commit()
            return True
        except exc.SQLAlchemyError as e:
            return {
                "error_code": e.code,
                "error_details": e._message(),
                "errors_sql": e._sql_message()
            }

class CartTotal(Resource):
    @ns_cart.response(HTTPStatus.OK,"Lista o total de produtos no carrinho")
    @ns_cart.response(HTTPStatus.BAD_REQUEST,"Falha ao contar registros!")
    @ns_cart.param("userType","Tipo do usuário","query",enum=['A','C','R'])
    @auth.login_required
    def get(self):
        userType = request.args.get("userType")
        # arrumar o codigo

        query = Select(func.count(distinct(tuple_(B2bCartShopping.id_product))).label("total"))\
            .select_from(B2bCartShopping)
            
        if userType=='R':
            #aqui precisa buscar todos os os do representante
            query = query.where(B2bCartShopping.id_customer.in_(
                Select(B2bCustomerGroupCustomers.id_customer)\
                .join(B2bCustomerGroup,B2bCustomerGroup.id==B2bCustomerGroupCustomers.id_customer_group))
            )
        else:
            id_entity = int(str(request.headers.get("x-entity")))
            query = query.where(B2bCartShopping.id_customer==id_entity)

        #zera o SQL se for admin
        if userType=='A':
            query = text("SELECT COUNT(DISTINCT (id_customer,id_product)) as total from b2b_cart_shopping")

        return db.session.execute(query).one().total if userType!='A' else db.session.execute(query).scalar()

ns_cart.add_resource(CartTotal,'/total/')