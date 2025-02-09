import os
from langchain_pinecone import PineconeVectorStore
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Pinecone
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pinecone.grpc import PineconeGRPC as Pinecone
import fitz
from dotenv import load_dotenv
from pinecone import ServerlessSpec

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENV = os.getenv('PINECONE_ENV')

pc = Pinecone(api_key=PINECONE_API_KEY)
embeddings = OpenAIEmbeddings(openai_api_key = OPENAI_API_KEY, model='text-embedding-ada-002')
client = OpenAI()

def main():
    pass
    # delete_pinecone_index('hackhive')
    # write_pinecone_index('hackhive')
    # write_to_text()

    # add_new_pdf('stats.pdf', 'hackhive')

    # query= "What textbook is recommended for stats course?"
    # print(generate_rag_answer(query, 'hackhive'))

'''

WRITING INTO PINECONE FUNCTIONS

'def add_new_pdf' doesn't do anything itself, but instead calls a series of functions
'write_to_text' will retrieve a pdf path and write the text into document.txt which will be overwritten each time
'write_pinecone_index' will create a new index if it doesn't exist, and then upload the text from document.txt into the Pinecone index

'''

def add_new_pdf(pdf_path, index_name):
    write_to_text(pdf_path)
    write_pinecone_index(index_name)

def write_to_text(pdf_path):
    pdf_document = fitz.open(pdf_path) 

    with open("document.txt", "w", encoding="utf-8", errors="replace") as text_file:
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            text = page.get_text()
            text_file.write(text + "\n")

    pdf_document.close()

def write_pinecone_index(index_name):
    if index_name not in pc.list_indexes().names():
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric='euclidean',
            spec=ServerlessSpec(
                cloud='aws',
                region=PINECONE_ENV
            )
        )

    file_data = open('document.txt', 'r', encoding="utf-8")
    file_content = file_data.read()

    # (the bigger the chunk_size, the context can get lost, overlap between chunks can help context)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=500
    )

    # Using the properties of text_splitter, split the entire text into smaller vectors
    doc_splits = text_splitter.create_documents([file_content])

    # Upload to VectorDB
    docsearch = Pinecone.from_documents(doc_splits, embeddings, index_name = index_name)
    print(f"Document has been added in {index_name}.")



'''

DELETE FUNCTION

'def delete_pinecone_index' deletes all the vectors within a PineconeDB

'''


def delete_pinecone_index(index_name):
    index = PineconeVectorStore(index_name=index_name, embedding=embeddings)
    index.delete(delete_all=True)
    print(f"All vectors in '{index_name}' have been deleted.")



'''

QUERY FUNCTIONS

'def generate_rag_answer' deletes all the vectors within a PineconeDB and calls upon all the other functions, eventually using all the other functions and creating a template for RAG
'def retrieve_query' embeds the user's query and returns the top 15 similar vectors
'def format_rag_prompt' formats the retrieved chunks as context and the user's query into a prompt for the RAG model

'''

def generate_rag_answer(query, index_name):
    retrieved_chunks = retrieve_query(query, 15, index_name)
    prompt = format_rag_prompt(query, retrieved_chunks)

    response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages = [
        {"role": "system", "content": "You are an AI assistant that answers queries based on retrieved documents. "
                                    "If you don't know the answer, please respond with: "
                                    "'Unfortunately, either what you're asking for doesn't exist or I don't quite understand the question. Can you please reword what you're asking?'"},
        {"role": "user", "content": prompt}
    ]

    )

    return response.choices[0].message.content

def retrieve_query(query, k, index_name):
    index = PineconeVectorStore(index_name=index_name, embedding=embeddings)
    matching_results = index.similarity_search(query, k=k)
    return matching_results

def format_rag_prompt(query, retrieved_chunks):
    prompt = f"""Use the following context to answer the question:

    {retrieved_chunks}

    Question: {query}

    Answer:
    """
    return prompt

if __name__ == '__main__':
    main()