import streamlit as st
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
import firebase_admin
from firebase_admin import credentials, auth, firestore, exceptions
import time
from datetime import datetime
from httpx_oauth.clients.google import GoogleOAuth2
import asyncio
from src.Oauth import *
import base64
import json

# Get keys from .env
load_dotenv()

# Page Title
st.set_page_config(page_title="Zotta Virtual Assistant", page_icon="🤖", layout='centered')

# Initialize Firebase 
if not firebase_admin._apps:
  key_dict = json.loads(st.secrets["textkey"])
  cred = credentials.Certificate(key_dict)
  firebase_admin.initialize_app(cred)

db = firestore.client()

# Sign in with google initialize
CLIENT_ID = st.secrets['CLIENT_ID']
CLIENT_SECRET = st.secrets['CLIENT_SECRET']
REDIRECT_URI = st.secrets['REDIRECT_URI']

# created_at
created_at = time.time()
date_time = datetime.fromtimestamp(created_at)
str_date_time = date_time.strftime("%d-%m-%Y, %H:%M:%S")

# Sticky Sidebar
st.markdown("""
<style>
  [data-testid="stSidebar"][aria-expanded="true"]{
    min-width: 275px;
    max-width: 350px;
  }""", unsafe_allow_html=True)

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

zottaImg = render_image('./src/zotta.png')

# Read the file and extract the content
def handleFileContext(file):
  file_reader = PdfReader(file)
  raw_text = ''
  for content in file_reader.pages:
    raw_text += content.extract_text()

  # Split into chunks
  text_splitter = CharacterTextSplitter(
    separator="\n", 
    chunk_size=1000, 
    chunk_overlap=200, 
    length_function=len
  )
  chunks = text_splitter.split_text(raw_text)
  
  # Generate embeddings for each chunk
  embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
  vector = FAISS.from_texts(chunks, embeddings)
  return vector

# Add data user to database 
def dataUser(email: str, username: str, created_at: str):
  # Check if user already is exist
  docs = db.collection('users').where('email', '==', email).stream()
  isUserExist = any(doc.exists for doc in docs)

  try:
    user = auth.get_user_by_email(email)

    if not isUserExist:
      db.collection('users').document(document_id=user.uid).set({
        'email': str(email),
        'username': str(username),
        'created_at': str(created_at)
      })
      
  except exceptions.FirebaseError as err: 
    user = auth.create_user(email=email)
    get_user = auth.get_user_by_email(email)

    if not isUserExist:
      db.collection('users').document(document_id=get_user.uid).set({
        'email': str(email),
        'username': str(username),
        'created_at': str(created_at)
      })

  return user

def home():
  try:
    user = auth.get_user_by_email(global_state.email)

    model_language = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-0125")

    with st.sidebar:
      get_user_by_uid = db.collection('users').document(user.uid).get()
      if get_user_by_uid.exists:
        username = get_user_by_uid.to_dict().get('username', 'user')
        st.markdown(f'''<p style="font-size: 18px; font-weight: 500; margin-bottom: 30px;">Welcome, {username}</p>''', unsafe_allow_html=True)
      
      upload_file = st.file_uploader('Upload your file', help='PDF', type=['pdf'])
      if upload_file is None:
        st.warning('You must upload a file before asking a question!')

      # Sign out button
      if st.button('Sign Out', type='primary', key='sign_out'):
        global_state.email = ''
        st.rerun()

    # Header
    st.markdown(f'''<div style="text-align: center; display: flex; justify-content: center; align-items: center; margin-top: -50px; margin-bottom: 20px;"><img src="{zottaImg}" alt="Logo app" style="width: 100px; height: 100px;" draggable="false"/></div>''', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; font-size: 32px; font-weight: 600;">Zotta</p>', unsafe_allow_html=True)

    container = st.container(border=True)

    prompt = st.chat_input('Send a message to Zotta')

    if upload_file is None and prompt is not None:
      st.error('You have to upload a file before continue!')

    # Process extract content from a pdf file
    if upload_file is not None:
      data_content = handleFileContext(upload_file)

      with st.spinner('Loading...'):
        if prompt != '' and prompt is not None:
          docs = data_content.similarity_search(prompt)
          prompt_template = """
            Answer the question as detailed as possible from the provided context, make sure to provide all the details, if the answer is not in
            provided context just say, "Pertanyaan tidak sesuai dengan materi yang diunggah.", don't provide the wrong answer\n\n
            Context:\n {context}?\n
            Question: \n{question}\n

            Answer:
            """
          promptTemp = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
          chain = load_qa_chain(model_language, chain_type='stuff', prompt=promptTemp)
          response = chain({"input_documents": docs, "question": prompt}, return_only_outputs=True)

          db.collection('chat_histories').document().set({
            'user_id': str(user.uid),
            'document_type': str(upload_file.type),
            'user_message': str(prompt),
            'bot_response': str(response['output_text']),
            'created_at': str(str_date_time)
          })

          container.chat_message('human').write(prompt)
          container.chat_message('assistant').write(f"Zotta : {response['output_text']}")
          
  except Exception as err:
    st.error(f"Something wrong, Please be sure upload a PDF file with valid content!")

# Sign In page
def signInPage(url = ''):
  st.markdown(f'''<div style="text-align: center; display: flex; justify-content: center; align-items: center; margin-top: -50px; margin-bottom: 20px;"><img src="{zottaImg}" alt="Logo app" style="width: 100px; height: 100px;" draggable="false"/></div>''', unsafe_allow_html=True)
  st.markdown('<p style="text-align: center; font-size: 32px; font-weight: 600; margin-bottom: 75px;">Zotta</p>', unsafe_allow_html=True)

  login_button = f"""
  <div style="display: flex; justify-content: center;">
    <a href="{url}" target="_blank" style="background-color: #CCD0FF; color: #111827; text-decoration: none; text-align: center; letter-spacing: 0.15px; font-weight: 600; font-size: 16px; margin: 4px 2px; cursor: pointer; padding: 10px 20px; border-radius: 8px; display: flex; align-items: center; gap: 8px">
      Sign In with google
      <img src="https://lh3.googleusercontent.com/COxitqgJr1sJnIDe8-jiKhxDx1FrYbtRHKJ9z_hELisAlapwE9LUPh6fcXIfb5vwpbMl4xl9H9TRFPc5NOO8Sb3VSgIBrfRYvW6cUA" alt="Google logo" style="margin-right: 8px; width: 23px; height: 23px; background-color: transparent; border: none; border-radius: 4px;">
      </a>
  </div>
  """
  st.markdown(login_button, unsafe_allow_html=True)

# Handle user authentication and redirection
def main(global_state):
  client = GoogleOAuth2(CLIENT_ID, CLIENT_SECRET)
  authorization_url = asyncio.run(
      get_authorization_url(client=client, redirect_uri=REDIRECT_URI))
  
  if not global_state.email:
    signInPage(authorization_url)
    try:
      # Get token from params
      token_from_params = get_token_from_params(client=client, redirect_uri=REDIRECT_URI)
    except Exception as err:
      return None
    
    # Decoding user token
    user_info = decode_user(token=token_from_params['id_token'])
    global_state.email = user_info['email']
    # Store the user to database
    dataUser(global_state.email, user_info['name'], str_date_time)
    st.query_params.clear()
    st.rerun()

  if global_state.email:
    home()
    st.query_params.clear()
  else:
    signInPage(authorization_url)
    

if __name__ == '__main__':
  # Initialization global state email
  class GlobalState:
    def __init__(self):
        self.email = ''

  if 'global_state' not in st.session_state:
    st.session_state.global_state = GlobalState()

  global_state = st.session_state.global_state

  main(global_state=global_state)