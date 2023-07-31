import pyspark
from pyspark.sql import SparkSession
from pyspark.sql.functions import expr

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    spark = SparkSession \
        .builder \
        .appName("File Streaming Demo") \
        .master("local[3]") \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .config("spark.sql.streaming.schemaInference", "true") \
        .getOrCreate()

    # sc = spark.sparkContext

    # Đọc dữ liệu từ file
    # Bạn cần config để Spark chỉ đọc nhiều nhất là 1 file mỗi batch
    raw_df = spark.readStream \
        .format("json") \
        .option("path", "input/data") \
        .option("maxFilesPerTrigger", "1")\
        .option("cleanSource", "delete")\
        .load()

    raw_df.printSchema()

    # Làm phẳng các phần tử của mảng InvoiceLineItems, bạn có thể sử dụng explode.
    explode_df = raw_df.selectExpr("InvoiceNumber", "CreatedTime", "StoreID", "PosID",
                                   "CustomerType", "PaymentMethod", "DeliveryType",
                                   "DeliveryAddress.City", "DeliveryAddress.State",
                                   "DeliveryAddress.Pincode", "explode(InvoiceLineItems) as LineItems")
    explode_df.printSchema()


    # Lấy các dữ liệu từ Dataframe
    flattened_df = explode_df \
        .withColumn("ItemCode", expr("LineItems.ItemCode")) \
        .withColumn("ItemDescription", expr("LineItems.ItemDescription")) \
        .withColumn("ItemPrice", expr("LineItems.ItemPrice")) \
        .withColumn("ItemQty", expr("LineItems.ItemQty")) \
        .withColumn("TotalValue", expr("LineItems.TotalValue")) \
        .drop("LineItem")

    # Lưu dữ liệu và tạo các checkpoint
    # Bạn hãy thiết lập để mỗi lần trigger cách nhau 1 phút và Output mode là Append
    invoiceWriterQuery = flattened_df.writeStream \
        .format("json") \
        .queryName("Flattened Invoice Writer") \
        .outputMode("append") \
        .option("path", "output/data") \
        .option("checkpointLocation", "chk-point-dir") \
        .trigger(processingTime="1 minute")\
        .start()

    print("Flattened Invoice Writer started")
    invoiceWriterQuery.awaitTermination()
