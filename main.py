import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAI, OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
import firebase_admin
from firebase_admin import credentials, auth, firestore, exceptions
import time
from datetime import datetime
from httpx_oauth.clients.google import GoogleOAuth2
import asyncio
from Oauth import *
import streamlit.components.v1 as components
import base64

# Get keys from .env
load_dotenv()

# Page Title
st.set_page_config(page_title="Zotta Chatbot with Document", page_icon="🤖", layout='centered')

# Initialize Firebase app
if not firebase_admin._apps:
  cred = credentials.Certificate("key.json")
  firebase_admin.initialize_app(cred)

# Firestore instance
db = firestore.client()

# Sign in with google initialize
CLIENT_ID = st.secrets['CLIENT_ID']
CLIENT_SECRET = st.secrets['CLIENT_SECRET']
REDIRECT_URI = 'http://localhost:8501/'

# Created_at
created_at = time.time()
# convert to datetime
date_time = datetime.fromtimestamp(created_at)
# convert Created_at to string
str_date_time = date_time.strftime("%d-%m-%Y, %H:%M:%S")

# Sticky Sidebar
st.markdown(
        """
       <style>
       [data-testid="stSidebar"][aria-expanded="true"]{
           min-width: 275px;
           max-width: 350px;
       }
       """,
        unsafe_allow_html=True)

# Button styles
st.markdown("""
<style>
div.stButton > button:first-child {
    background-color: #D10000;
    color: #f3f4f6;
    border: none;
    padding: 8px 20px;
    transition: background-color 0.2s ease-in-out;
} 
div.stButton > button:hover {
    background-color: #b30000;
} 
</style>""", unsafe_allow_html=True) 

# Rendering image using base64
def render_image(filepath: str):
  with open(filepath, 'rb') as f:
    data = f.read()
  content_encode = base64.b64encode(data).decode()
  image_string = f'data:image/png;base64,{content_encode}'
  return image_string

# Zotta image
zottaImg = render_image('./src/zotta.png')

# Handle upload file
def sidebar():
  with st.sidebar:
    # User profile
    user = auth.get_user_by_email(global_state.email)
    get_user_by_uid = db.collection('users').document(user.uid).get()

    if get_user_by_uid.exists:
      username = get_user_by_uid.to_dict().get('username')
      st.markdown(f'''<p style="font-size: 18px; font-weight: 500; margin-bottom: 30px;">Welcome, {username}</p>''', unsafe_allow_html=True)
    
    # Upload file/document
    file_uploader = st.file_uploader('Upload your document', help='PDF or CSV only', type=['pdf', 'csv'])

    # Check if file isn't uploaded
    if file_uploader is None:
      st.warning('Please upload a file before continue!')

    # Sign out button
    if st.button('Sign Out', type='primary', key='sign_out'):
      global_state.email = ''
      st.rerun()

    for _space in range(4):
      st.write("\n")

    # Footer
    st.markdown('<p style="text-align: center; font-size: 13px; font-weight: 400; opacity: 0.8; margin-top: auto;">Zotta may provide inaccurate information, Consider checking important information.</p>', unsafe_allow_html=True)

    return file_uploader

# Handle process file pdf
def handleFilePDF(file):
  # Read the file/document PDF
  file_reader = PdfReader(file)

  # Extract all text of the file into raw_text 
  raw_text = ''
  for content in file_reader.pages:
    raw_text += content.extract_text()

  # Split it into chunks
  text_split = CharacterTextSplitter(
    separator="\n", 
    chunk_size=1000, 
    chunk_overlap=200, 
    length_function=len
  )
  chunks = text_split.split_text(raw_text)
  
  # Embeddings instance
  embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
  # Convert it into embeddings using FAISS
  create_embeddings = FAISS.from_texts(chunks, embeddings)

  return create_embeddings

# Handle process file csv
def handleFileCSV(llm, file):
  # Read the file/document CSV
  df = pd.read_csv(file)

  # Construct pandas agent
  agent = create_pandas_dataframe_agent(llm, df, verbose=True)

  return agent

# Add data user to firestore
def dataUser(email: str, username: str, created_at: str):
  # If user already exists in the collection firestore don't add new user
  docs = db.collection('users').where('email', '==', email).stream()
  isUserExists = any(doc.exists for doc in docs)

  try:
    user = auth.get_user_by_email(email)
    user_id = user.uid

    if not isUserExists:
      db.collection('users').document(document_id=user_id).set({
        'email': str(email),
        'username': str(username),
        'created_at': str(created_at)
      })
  except exceptions.FirebaseError as e: 
    user = auth.create_user(email=email)
    get_user = auth.get_user_by_email(email)
    user_id = get_user.uid

    if not isUserExists:
      db.collection('users').document(document_id=user_id).set({
        'email': str(email),
        'username': str(username),
        'created_at': str(created_at)
      })

  return user

def home():
  try:
    # Header
    st.markdown(f'''<div style="text-align: center; display: flex; justify-content: center; align-items: center; margin-top: -50px; margin-bottom: 20px;"><img src="{zottaImg}" alt="Logo app" style="width: 100px; height: 100px; "/></div>''', unsafe_allow_html=True)

    st.markdown('<p style="text-align: center; font-size: 32px; font-weight: 600;">Zotta</p>', unsafe_allow_html=True)

    # Container content
    container = st.container(border=True)

    # OpenAI instance
    llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-0125")

    # Instance upload file
    upload_file = sidebar()

    if upload_file is not None:
      # Handle PDF file
      if upload_file.type == 'application/pdf':
        data_pdf = handleFilePDF(upload_file)

      # Handle CSV file
      elif upload_file.type == 'text/csv':
        data_csv = handleFileCSV(llm, upload_file)        

    # User prompt
    prompt = st.chat_input('Send a message to Zotta')

    with st.spinner('Loading...'):
      if prompt != '' and prompt is not None:
        user = auth.get_user_by_email(global_state.email)

        # Handle prompt based on PDF file 
        if upload_file.type == 'application/pdf':
          # Similarity search
          docs = data_pdf.similarity_search(prompt)

          # Process Question answering
          chain = load_qa_chain(llm, chain_type='stuff')
          response_pdf = chain.run(input_documents=docs, question=prompt)

          # Store the result to chat histories collection
          db.collection('chat_histories').document().set({
            'user_id': str(user.uid),
            'document_type': str(upload_file.type),
            'user_message': str(prompt),
            'bot_response': str(response_pdf),
            'created_at': str(str_date_time)
          })

          # Output message
          container.chat_message('human').write(prompt)
          container.chat_message('assistant').write(f"Zotta : {response_pdf}")

        # Handle prompt based on CSV file 
        elif upload_file.type == 'text/csv':
          # Agent process to thinking
          response_csv = data_csv.run(prompt)

          # Store the result to chat histories collection
          db.collection('chat_histories').document().set({
            'user_id': str(user.uid),
            'document_type': str(upload_file.type),
            'user_message': str(prompt),
            'bot_response': str(response_csv),
            'created_at': str(str_date_time)
          })

          # Output message
          container.chat_message('human').write(prompt)
          container.chat_message('assistant').write(f"Zotta : {response_csv}")

        else:
          st.error('Something wrong, try again!')
          
  except Exception as err:
    st.error(f"Something wrong, Please be sure upload a file or the file format!")

# Sign In page
def signInPage(url = ''):
  components.html(f""" 
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" integrity="sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm" crossorigin="anonymous">
    <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js" integrity="sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN" crossorigin="anonymous"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>

    <style>
      body {{
        background-color: #1e293b;
      }}
      .custom_layout {{
        width: 300px;
      }}
      .btn-primary {{
        background-color: #CCD0FF;
        color: #111827;
        font-weight: 500;
        border: none;
        padding: 10px 0;
        font-size: 16px;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
        border-radius: 8px;
        transition: all 0.2s ease-in-out;
      }}
      .btn-primary:hover {{
        background-color: #b3b9ff;
        color: #111827;
      }}                   
      .google_icon {{
        width: 20px;
        height: auto;
        text-align: center;
        display: flex;
        align-items: center;
      }}
      </style>
                  
      <div class="container mx-auto text-center">
        <div class="row justify-content-center">
          <div class="col-md-3 text-center mt-5 custom_layout">
            <a href="{url}" target="_blank" class="btn btn-primary">
              Sign In with google
              <div class="google_icon">
                <svg xmlns="http://www.w3.org/2000/svg" height="100%" viewBox="0 0 24 24" width="100%" fit="" preserveAspectRatio="xMidYMid meet" focusable="false"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"></path><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"></path><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"></path><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"></path><path d="M1 1h22v22H1z" fill="none"></path></svg> 
              </div>
            </a>
          </div>
        </div>
      </div>
""", height=200)

def main(global_state, inner_call=False):
  client: GoogleOAuth2 = GoogleOAuth2(CLIENT_ID, CLIENT_SECRET)
  authorization_url = asyncio.run(
      get_authorization_url(client=client, redirect_uri=REDIRECT_URI))
  
  if not global_state.email:
    signInPage(authorization_url)
    try:
      # Getting token from params
      token_from_params = get_token_from_params(client=client, redirect_uri=REDIRECT_URI)
    except Exception as err:
      return None
    
    # Decoding user using jwt
    user_info = decode_user(token=token_from_params['id_token'])
    global_state.email = user_info['email']
    username = user_info['name']
    # Store the user to users collection
    dataUser(global_state.email, username, str_date_time)
    st.rerun()

  if inner_call:
    user_email = global_state.email
    if not user_email:
      signInPage(authorization_url)
      
    if user_email:
      home()

  if not inner_call:
    signInPage(authorization_url)


if __name__ == '__main__':
  main(global_state=global_state, inner_call=True)