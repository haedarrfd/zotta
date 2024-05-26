import streamlit as st
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
import firebase_admin
from firebase_admin import credentials, firestore
import time
from datetime import datetime
import base64

# Get keys from .env
load_dotenv()

# Page Title
st.set_page_config(page_title="Zotta Chatbot with Document", page_icon="🤖", layout='centered')

# Initialize Firebase 
if not firebase_admin._apps:
  cred = credentials.Certificate("key.json")
  firebase_admin.initialize_app(cred)

db = firestore.client()

# created_at
created_at = time.time()
date_time = datetime.fromtimestamp(created_at)
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

def home():
  try:
    model_language = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-0125")

    with st.sidebar:      
      upload_file = st.file_uploader('Upload your file', help='PDF', type=['pdf'])
      if upload_file is None:
        st.warning('Please upload a file before continue!')

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
            'document_type': str(upload_file.type),
            'user_message': str(prompt),
            'bot_response': str(response['output_text']),
            'created_at': str(str_date_time)
          })

          container.chat_message('human').write(prompt)
          container.chat_message('assistant').write(f"Zotta : {response['output_text']}")
          
  except Exception as err:
    st.error(f"Something wrong, Please be sure upload a file or the file format! {err}")

if __name__ == '__main__':
  home()