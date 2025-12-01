import os
import filetype
import importlib
from auth import auth
from flask import request
from http import HTTPStatus
from datetime import datetime
from models.helpers import db
from werkzeug import exceptions
from f2bconfig import EntityAction
from flask_restx import Resource, Namespace
from sqlalchemy import Select, Update, Delete, func
from models.tenant import _save_entity_log, CmmLegalEntities, CmmLegalEntityFile, CmmProductsImages

ns_upload = Namespace("upload",description="Operações para manipular upload de dados")

@ns_upload.route("/<int:id>")
class UploadApi(Resource):
    @ns_upload.response(HTTPStatus.OK,"Realiza envio de arquivo(s) da LegalEntity para o servidor")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @ns_upload.param("files[]","Arquivo a ser enviado para o servidor","formData")
    @auth.login_required
    def post(self,id:int):
        try:
            newFileName = ''
            #obtem os arquivos para upload
            files = []
            fileCount = 1
            fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/'
            for ufile in request.files.getlist('files[]'):
                parts = str(ufile.filename).split(".")
                ext = parts[len(parts)-1]
                if ext=='pdf':
                    ffolder = "pdf/"
                elif ext=='doc' or ext=='docx' or ext=='xls' or ext=='xlsx' or ext=='ppt' or ext=='pptx':
                    ffolder = "docs/"
                elif ext=='txt' or ext=='html' or ext=='rtl' or ext=='csv':
                    ffolder = "docs/"
                elif ext=='png' or ext=='jpeg' or ext=='jpg' or ext=='bmp' or ext=='gif' or ext=='svg' or ext=='tiff':
                    ffolder = "images/"
                elif ext=='cer' or ext=='p7b' or ext=='pfx' or ext=='p12':
                    ffolder = "certs/"
                else:
                    ffolder = "unclassified/"


                #busca as informacoes de cliente para salvar o arquivo
                #tambem atribui um novo nome ao arquivo
                entity = db.session.execute(Select(CmmLegalEntities.taxvat).where(CmmLegalEntities.id==id)).first()
                if entity is not None:
                    #salva o arquivo com outro nome
                    newFileName = entity.taxvat+"_"+str(fileCount)+"_"+datetime.now().strftime("%Y%m%d-%H%M%S")+"."+ext
                    files.append(newFileName)
                    ufile.save(fpath+ffolder+newFileName)

                    #salva os dados do arquivo no cadastro do cliente
                    file:CmmLegalEntityFile = CmmLegalEntityFile()
                    setattr(file,"id_legal_entity",id)
                    setattr(file,"content_type",('Arquivo '+ext if filetype.guess_mime(fpath+ffolder+newFileName) is None else filetype.guess_mime(fpath+ffolder+newFileName)))
                    setattr(file,"folder",ffolder)
                    file.name = newFileName
                    db.session.add(file)
                    db.session.commit()
                fileCount += 1

            combinedFiles = ','.join(files)
            _save_entity_log(id,EntityAction.FILE_ATTACHED,"Adicionado(s) o(s) arquivo(s) "+combinedFiles)

            return True
        except exceptions.HTTPException as e:
            print("Exception")
            print(e.get_headers())
            return False

    @ns_upload.response(HTTPStatus.OK,"Realiza a exclusão de arquivo(s)")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao excluir arquivo(s)!")
    @auth.login_required
    def delete(self,id:int):
        try:
            file = db.session.execute(Select(CmmLegalEntityFile.name,
                                             CmmLegalEntityFile.folder,
                                             CmmLegalEntityFile.id_legal_entity,
                                             CmmLegalEntityFile.content_type,
                                             CmmLegalEntityFile.date_created,
                                             CmmLegalEntityFile.date_updated).where(CmmLegalEntityFile.id==id)).first()
            if file is not None:
                if os.path.exists(str(os.environ.get("F2B_APP_PATH"))+'assets/'+str(file.folder)+str(file.name)):
                    os.remove(str(os.environ.get("F2B_APP_PATH"))+'assets/'+str(file.folder)+str(file.name))
                    db.session.execute(Delete(CmmLegalEntityFile).where(CmmLegalEntityFile.id==id))
                    db.session.commit()
                    _save_entity_log(file.id_legal_entity,EntityAction.FILE_DETTACHED,'Removido o arquivo '+file.name)
                return True
        except exceptions.HTTPException:
            return False
        

class UploadTmp(Resource):
    @ns_upload.response(HTTPStatus.OK,"Realiza envio de arquivo(s) para o servidor na pasta temporaria")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @auth.login_required
    def post(self):
        try:
            #obtem os arquivos para upload
            fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/tmp/'
            for file in request.files.getlist('files[]'):
                file.save(fpath+str(file.filename))

            return True
        except exceptions.HTTPException as e:
            print(e)
            return False
ns_upload.add_resource(UploadTmp,'/temp')

@ns_upload.route("/<int:id>/<int:idprod>/<int:idcolor>/<int:idsize>")
class UploadDevolution(Resource):
    @ns_upload.response(HTTPStatus.OK,"Realiza envio de arquivo(s) para o servidor na pasta temporaria")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @auth.login_required
    def post(self,id:int,idprod:int,idcolor:int,idsize:int):
        try:
            files = []
            #obtem os arquivos para upload
            fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/tmp/'
            if os.path.exists(fpath)==False:
                os.mkdir(fpath)
            file_count = 1
            for file in request.files.getlist('files[]'):
                parts = str(file.filename).split(".")
                ext = parts[len(parts)-1]
                newFileName = "devolution_"+str(id)+"_"+str(idprod)+"_"+str(idcolor)+"_"+str(idsize)+"_"+str(file_count)+"."+ext
                file.save(fpath+newFileName)
                file.close()
                file_count += 1
                files.append(newFileName)
            return files
        except exceptions.HTTPException as e:
            print(e)
            return False
ns_upload.add_resource(UploadDevolution,'/devolution/<int:id>/<int:idprod>/<int:idcolor>/<int:idsize>')

class UploadImport(Resource):
    @ns_upload.response(HTTPStatus.OK,"Realiza envio de arquivo(s) para o servidor na pasta de importação")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @auth.login_required
    def post(self):
        try:
            customer = request.headers.get("x-customer")
            if request.args.get("type")=='E':
                type = request.headers.get("x-entity-model")
            elif request.args.get("type")=='P':
                type = "product"

            files = []
            #obtem os arquivos para upload
            fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/import/'
            if os.path.exists(fpath)==False:
                os.mkdir(fpath)
            for file in request.files.getlist('files[]'):
                parts = str(file.filename).split(".")
                ext = parts[len(parts)-1]
                newFileName = "import_"+str(customer)+"_"+str(type)+"_"+datetime.now().strftime("%Y%m%d-%H%M%S")+"."+ext
                file.save(fpath+newFileName)
                file.close()
                files.append(newFileName)
            return files
        except exceptions.HTTPException as e:
            print(e)
            return False
ns_upload.add_resource(UploadImport,'/import/')


class UploadProduct(Resource):
    @ns_upload.response(HTTPStatus.OK,"Realiza envio de arquivo(s) de produto(s) para o servidor")
    @ns_upload.response(HTTPStatus.BAD_REQUEST,"Falha ao enviar arquivo(s)!")
    @auth.login_required
    def post(self,id:int):
        try:
            files = []
            #obtem os arquivos para upload
            for file in request.files.getlist('files[]'):
                if os.environ.get("F2B_COMPANY_UPLOAD_IMAGE")=="local":
                    fpath = str(os.environ.get("F2B_APP_PATH"))+'assets/images/'
                    if os.path.exists(fpath)==False:
                        os.mkdir(fpath)
                    parts = str(file.filename).split(".")
                    ext = parts[len(parts)-1]
                    newFileName = "product_"+datetime.now().strftime("%Y%m%d-%H%M%S")+"."+ext
                    file.save(fpath+newFileName)
                    file.close()
                    files.append(newFileName)
                else:

                    # limpa todos os arquivos da pasta temporaria
                    for filename in os.listdir(str(os.environ.get("F2B_APP_PATH"))+'assets/tmp'):
                        os.unlink(str(os.environ.get("F2B_APP_PATH"))+'assets/tmp/'+filename)

                    newFileName = "product_"+str(file.filename)
                    module = str(os.environ.get("F2B_COMPANY_UPLOAD_IMAGE"))
                    class_name = str(os.environ.get("F2B_COMPANY_UPLOAD_IMAGE")).replace("_"," ").title().replace(" ","")
                    FILE_OBJ = getattr(
                    importlib.import_module('integrations.files.'+module),
                    class_name
                    )
                    fl = FILE_OBJ()
                    if fl.send(newFileName,"products",file) is True:
                        nNewFileName = fl.get(newFileName,"products")
                    files.append(nNewFileName)

            # remove o default existente para garantir que nao haverao 2
            db.session.execute(Update(CmmProductsImages).values(img_default=False).where(CmmProductsImages.id_product==id))
            db.session.commit()

            i = 0 
            for f in files:
                fUrl = str(os.environ.get("F2B_APP_URL"))+"assets/images/"+f if os.environ.get("F2B_COMPANY_UPLOAD_IMAGE")=="local" else ""+f
                exist = db.session.execute(Select(func.count(CmmProductsImages.id).label("total")).where(CmmProductsImages.img_url==fUrl)).first()
                # so irah incluir se a imagem nao existir
                if exist is None or exist.total == 0:
                    img = CmmProductsImages()
                    setattr(img,"img_default",(True if i == 0 else False))
                    setattr(img,"id_product",id)
                    img.img_url = fUrl
                    db.session.add(img)
                db.session.commit()
                i += 1

            return files
        except exceptions.HTTPException as e:
            print(e)
            return False
ns_upload.add_resource(UploadProduct,'/products/<int:id>')


class UploadProductReturn(Resource):
    def get(self):
        try:
            pass
        except Exception:
            pass
ns_upload.add_resource(UploadProductReturn,'/products/')