from pinecone.grpc import PineconeGRPC as Pinecone

pc = Pinecone(api_key="pcsk_dw2X3_3GNh2P6qfanr1eUf6jb5qbwuRDTKYLSDCPvvqsgiWpp9zrkSyuD7MTVMoB6czq8")

index_list = pc.list_indexes()

print(index_list)