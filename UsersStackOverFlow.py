from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as f
from pyspark.sql.functions import col, when, udf, lit, sum, explode, substring_index, to_date, expr, count
from pyspark.sql.types import StringType, IntegerType, DateType, ArrayType
import re

def parse_ownerUserId(id):
    ''' Đưa các dữ liệu null và không đúng định dạng về mặc định '-1'. '''
    try:
        int(id)
        return id
    except ValueError:
        return '-1'

if __name__ == '__main__':
    spark = SparkSession.builder.appName("Assignment16")\
                        .master('local') \
                        .config('spark.jars.packages', 'org.mongodb.spark:mongo-spark-connector_2.12:3.0.1') \
                        .config('spark.mongodb.input.uri', 'mongodb://localhost/stackOverFlow') \
                        .config('spark.mongodb.output.uri', 'mongodb://localhost/output_stackOverFlow') \
                        .getOrCreate()

    # Chuẩn hóa dữ liệu dataframe questions
    qt_df = spark.read \
        .format('com.mongodb.spark.sql.DefaultSource') \
        .option("uri", 'mongodb://localhost/stackOverFlow.questions')\
        .load(inferSchma=False)
    parse_ownerUserId_udf = udf(parse_ownerUserId, returnType=StringType())
    qt_df = qt_df.withColumn('OwnerUserId', parse_ownerUserId_udf('OwnerUserId').cast(IntegerType()))
    qt_df = qt_df.withColumn('CreationDate', col('CreationDate').cast(DateType()))
    qt_df = qt_df.withColumn('ClosedDate', when(col('ClosedDate') == 'NA', None).otherwise(col("ClosedDate")).cast(DateType())).drop('_id')
    
    # Chuẩn hóa dữ liệu dataframe answers
    aw_df = spark.read \
        .format('com.mongodb.spark.sql.DefaultSource') \
        .option("uri", 'mongodb://localhost/stackOverFlow.answers') \
        .load(inferSchma=False)
    aw_df = aw_df.withColumn('CreationDate', col('CreationDate').cast(DateType()))
    aw_df = aw_df.withColumn('OwnerUserId', parse_ownerUserId_udf('OwnerUserId').cast(IntegerType())).drop('_id')

    print("+------------------------------MENU----------------------------------+")
    print("|   1. Tính số lần xuất hiện của các ngôn ngữ lập trình              |")
    print("|   2. Tìm các domain được sử dụng nhiều nhất trong các câu hỏi      |")
    print("|   3. Tính tổng điểm của User theo từng ngày                        |")
    print("|   4. Tính tổng số điểm mà User đạt được trong một khoảng thời gian |")
    print("|   5. Tìm các câu hỏi có nhiều câu trả lời                          |")
    print("|   6. Tìm các Active User                                           |")
    print("|   0. Exit                                                          |")
    print("+--------------------------------------------------------------------+")
    key = input("+-------------- Please choose feature...")

    if key == '0':
        print("Thanks!")

    elif key == '1':
        #region Tính số lần xuất hiện của các ngôn ngữ lập trình
        def find_languge(body, languague): # Tìm số lần xuất hiện của ngôn ngữ lập trình trong body. Có cách khác là return ra mảng ngôn ngữ --> Explode mảng và đếm sẽ cho tốc độ nhanh hơn nhiều
            pattern = r"\b" + re.escape(languague.lower()) + r"\b"
            result = re.findall(pattern, body.lower())
            return len(result)

        find_languge_udf = udf(find_languge, returnType=IntegerType())
        programming_languages = ["Java", "Python", "C++", "C#", "Go", "Ruby", "Javascript", "PHP", "HTML", "CSS", "SQL"]

        # temp = qt_df.select(col('Body').alias("Body"),[find_languge_udf('Body', lit(lang)).alias(lang) for lang in programming_languages])
        # temp.show()
        expr_columns = [find_languge_udf(col('Body'), lit(lang)).alias(lang) for lang in programming_languages]
        temp = qt_df.select(col('Body'), *expr_columns)
        result = temp.select([sum(col(lang)).alias(lang) for lang in temp.columns])
        result.show()
        #endregion

    elif key == '2':
        #region Tìm các domain được sử dụng nhiều nhất trong các câu hỏi

        def find_url(body): # Tìm các url xuất hiện trong body
            pattern =r'href="([^"]*)"'
            result = re.findall(pattern, body.lower())
            return result

        find_language_udf = udf(find_url, returnType=ArrayType(StringType()))
        array_url_df = qt_df.withColumn('array_url', find_language_udf(col('Body')))
        url_df = array_url_df.select(explode('array_url').alias('url'))
        result = url_df.withColumn("url", substring_index('url', "/", 3)) \
            .groupBy('url') \
            .count()\
            .orderBy('count', ascending=False)\
            .filter((col('url') != "#") & (col('url') != ""))
        result.show(truncate=False)
        #endregion

    elif key == '3':
        #region Tính tổng điểm của User theo từng ngày

        union_df = qt_df.select("OwnerUserId", "CreationDate", "Score").union(aw_df.select("OwnerUserId", "CreationDate", "Score")).filter((col('OwnerUserId') != -1))
        score_window = Window.partitionBy("OwnerUserId").orderBy("CreationDate").rowsBetween(Window.unboundedPreceding, Window.currentRow)
        union_df.withColumn("Total", f.sum("Score").over(score_window)).show()
        #endregion

    elif key == '4':
        #region Tính tổng số điểm mà User đạt được trong một khoảng thời gian. 

        # Task này chưa đưa START và END vào được vì bị lỗi, chưa fix được
        START = '01-01-2008'
        END = '01-01-2009'
        union_df = qt_df.select("OwnerUserId", "CreationDate", "Score")\
            .union(aw_df.select("OwnerUserId", "CreationDate", "Score")) \
            .withColumn("CreationDate", to_date("CreationDate", "dd-MM-yyyy"))\
            .filter((col('OwnerUserId') != -1))\
            # .filter(col("CreationDate") >= lit(START).cast('date'))

        union_df = union_df.groupBy("OwnerUserId").agg(sum("Score").alias("TotalScore"))
        union_df.show()
        #endregion

    elif key == '5':
        #region Tìm các câu hỏi có nhiều câu trả lời

        aw_rename_df = aw_df.withColumnRenamed("Id", "AnswerId")
        join_key = qt_df.Id == aw_df.ParentId
        joined_df = qt_df.join(aw_rename_df, join_key, "inner").drop(aw_df.Body, aw_df.CreationDate, aw_df.ParentId, aw_df.Score, aw_df.OwnerUserId)\
                        .select("Id", "OwnerUserId", "Title", "AnswerId")\
                        .groupBy("Id").count().orderBy('Id', ascending=True)
        joined_df.show()
        #endregion

    elif key == 6:
        #region Tìm các Active User. 

        # Tiêu chí của Active User: Hoặc có tổng số câu trả lời trên 50 lần, hoặc có tổng số điểm trên 500 hoặc có 5 câu trả lời trong 1 ngày trong 1 câu hỏi nhất định
        qt_createDate_df = qt_df.select("Id", "CreationDate").withColumnRenamed("CreationDate", "QDate")
        join_key = qt_df.Id == aw_df.ParentId
        active_id_df = aw_df.join(qt_createDate_df, join_key, "inner") \
            .withColumn("SameDate", expr("case when CreationDate == QDate then 1 else 0 end")) \
            .groupBy("OwnerUserId") \
            .agg(count("*").alias("TotalAnswer"),
                 sum("Score").alias("TotalScore"),
                 sum("SameDate").alias("TotalSameDate")) \
            .where(((col("TotalAnswer") > 50) | (col("TotalScore") > 500) | (col("TotalSameDate") > 5))
                   & (col("OwnerUserId") != -1)) \
            .select(col("OwnerUserId").alias("ActiveId")) \
            .orderBy("ActiveId")
        active_id_df.show()
        #endregion