import csv
import logging
import importlib
from flimv import Flimv
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import Insert, create_engine, Select
from os import environ, path, listdir, remove
from concurrent.futures import ThreadPoolExecutor
from models.public import SysCustomer, SysConfig
from models.tenant import CmmLegalEntityImport, CmmProductsImport


BASEDIR = path.abspath(path.dirname(__file__))
load_dotenv(path.join(BASEDIR, '.env'))

# realiza a conexao com o banco de dados (repensar para incluir os tenants)
conn = str(environ.get("F2B_DB_LIB"))+"://"
conn += str(environ.get("F2B_DB_USER"))+":"
conn += str(environ.get("F2B_DB_PASS"))+"@"
conn += str(environ.get("F2B_DB_HOST"))+"/"
conn += str(environ.get("F2B_DB_NAME"))
db = create_engine(conn)

with db.connect() as connection:
    try:
        # verifica se a tabela de importacao de produtos existe, senao cria
        all_active_customers = connection.execute(Select(SysCustomer.id,SysConfig.erp_integration,SysConfig.erp_module).where(SysCustomer.churn.is_(False)))
    except Exception as e:
        logging.error(e)


# esse eh o job de carga do ERP que eh executado de hora em hora
if datetime.now().strftime("%M")=="00":
    for customer in all_active_customers:
        if customer.erp_integration==True:
            module = str(customer.erp_module)
            class_name = str(customer.erp_module).replace("_"," ").title().replace(" ","")
            ERP = getattr(
                importlib.import_module('integrations.erp.'+module),
                class_name
            )

        # cria uma instancia do ERP para cada cliente
        erp = ERP(customer.id)

        erp.get_representative()
        erp.get_customer()
        erp.get_order()
        erp.get_invoice()
        erp.get_payment_conditions()
        erp.get_products()
        erp.get_bank_slip()
        erp.get_measure_unit()
        erp.create_order()

# esse eh o job que atualiza as informacoes do FLIMV a cada dia sempre as 1h
# if datetime.now().strftime("%H%M")=="0100":
if datetime.now().strftime("%H%M")=="1040":
    for customer in all_active_customers:
        # cria uma instancia do FLIMV para cada cliente
        flimv = Flimv(customer.id)
        flimv.process()


def import_file(fName:str):
    try:
        with open(fName,newline='',encoding="utf-8") as csv_file:
            has_header = csv.Sniffer().has_header(csv_file.read(1024))
            csv_file.seek(0)
            csv_reader = csv.reader(csv_file)
            #pula a linha de cabecalho
            if has_header:
                next(csv_reader)
            with db.connect() as conn:
                customers = conn.execute(Select(SysCustomer.id).where(SysCustomer.churn.is_(False)))
                for customer in customers:
                    nconn = create_engine(str(environ.get("F2B_DB_LIB"))+"://"+str(environ.get("F2B_DB_USER"))+":"+\
                        str(environ.get("F2B_DB_PASS"))+"@"+str(environ.get("F2B_DB_HOST"))+"/"+str(environ.get("F2B_DB_NAME"))+"?options=-c%20search_path="+str(customer.id))
                    ndb = nconn.connect()
                    
                    if fName.find("import_P_")!=-1:
                        for row in csv_reader:
                            product = {
                                "refCode":row[0],
                                "barCode":row[1],
                                "type":row[2],
                                "model":row[3],
                                "brand":row[4],
                                "name":row[5],
                                "description":row[6],
                                "observation":row[7],
                                "price":float(str(row[8]).replace(",",".")),
                                "measure_unit":row[9],
                                "color":row[10],
                                "size":row[11],
                                "quantity":int(row[12])
                            }
                            ndb.execute(Insert(CmmProductsImport),product)
                    elif fName.find("import_E_")!=-1:
                        for row in csv_reader:
                            entity = {
                                "id_original":row[0],
                                "taxvat":row[1],
                                "name":row[2],
                                "fantasy_name":row[3],
                                "city":row[4],
                                "postal_code":row[5],
                                "neighborhood":row[6],
                                "address":row[7],
                                "type": "P" if row[8]=='PERSONA' else "C" if row[8]=="CUSTOMER" else "R",
                                "phone_type":row[9],
                                "phone_number":row[10],
                                "is_whatsapp":bool(row[11]),
                                "phone_is_default":bool([row[12]]),
                                "email_type":row[13],
                                "email_address":row[14],
                                "email_is_default":bool(row[15])
                            }
                            ndb.execute(Insert(CmmLegalEntityImport),parameters=entity)
                    ndb.commit()
            #fecha o arquivo
            csv_file.close()

            #realiza a exclusao do arquivo apos importar
            remove(fName)
            process_import()
    except Exception as e:
        logging.error(e)
        print(e)

def process_import():
    try:
        pass
    except Exception as e:
        logging.error(e)

# realiza varredura dos arquivos de importacao e adiciona um em cada thread para execucao
# mesmo por que nao deverao haver muitas importacoes de dados
fpath = str(environ.get("F2B_APP_PATH"))+'assets/import/' 
files = [f for f in listdir(fpath) if path.isfile(fpath+f)]
workers = len(files)+1
for f in files:
    # define uma thread para cada arquivo existente
    with ThreadPoolExecutor(max_workers=workers) as executor:
        ft = executor.submit(import_file,fpath+f)
        print(executor._work_queue)
        print(f)
        #if ft.done:
            # print(executor._work_queue)
        # executor.shutdown(wait=True)