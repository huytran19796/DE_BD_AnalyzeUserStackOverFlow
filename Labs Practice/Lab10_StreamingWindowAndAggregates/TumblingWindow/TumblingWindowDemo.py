from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, to_timestamp, expr, window, sum
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

if __name__ == '__main__':
    spark = SparkSession.builder.appName("TumblingWindow")\
                        .master('local[3]')\
                        .config('spark.streaming.stopGracefullyOnShutdown', 'true')\
                        .config('spark.sql.shuffle.partitions', 2)\
                        .getOrCreate()

    stock_schema = StructType([
        StructField('CreatedTime',StringType()),
        StructField('Type', StringType()),
        StructField('Amount', IntegerType()),
        StructField('BrokerCode', StringType()),
    ])

    # Đọc dữ liệu từ Kafka
    kafka_df = spark.readStream.format('kafka')\
                    .option('kafka.bootstrap.servers','localhost:9092')\
                    .option('subscribe','trades') \
                    .option('startingOffsets', 'earliest')\
                    .load()

    # Chuyển dữ liệu từ dạng JSON về MapType()
    value_df = kafka_df.select(from_json(col('value').cast('string'),stock_schema).alias('value'))

    trade_df = value_df.select('value.*').withColumn('CreatedTime',to_timestamp(col('CreatedTime'), 'yyyy-MM-dd HH:mm:ss'))\
                .withColumn('Buy', expr("CASE WHEN Type == 'BUY' THEN Amount else 0 END")) \
                .withColumn('Sell', expr("CASE WHEN Type == 'SELL' THEN Amount else 0 END"))

    # Sử dụng cơ chế Tumbling Window
    window_agg_df = trade_df.groupBy(window(col("CreatedTime"), "15 minute"))\
                        .agg(sum("Buy").alias("TotalBuy"), sum("Sell").alias("TotalSell"))

    output_df = window_agg_df.select('window.start', 'window.end', 'TotalBuy', 'TotalSell')

    window_query = output_df.writeStream\
                    .format("console")\
                    .outputMode('update')\
                    .option('checkpointLocation', 'chk-point-dir')\
                    .trigger(processingTime='1 minute')\
                    .start()
    print("Waiting for Query")
    window_query.awaitTermination()