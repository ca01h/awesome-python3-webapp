# -*-coding:utf-8-*-

import logging, aiomysql

logging.basicConfig(level=logging.INFO)
__author__ = 'caoyihuai'

import asyncio, logging
import aiomysql


@asyncio.coroutine
def destroy_pool():  # 销毁连接池
    global __pool
    if __pool is not None:
        __pool.close()
        yield from  __pool.wait_closed()


# 打印SQL查询语句
def log(sql, args=()):
    logging.info('SQL: %s' % (sql))


# 创建一个全局的连接池，每个Http请求都从池中获得数据库的连接
@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create database connection pool...')

    # 全局变量__pool用于存储整个连接池
    global __pool
    __pool = yield from aiomysql.create_pool(
        # **kw参数可以包含所有连接需要用到的关键字参数
        # 默认本机IP
        host=kw.get('host', 'localhost'),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        port=kw.get('port', 3306),
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        # 默认最大连接数为10
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        # 接收一个Loop实例
        loop=loop
    )


# 封装SQL select语句为 select函数
def select(sql, args, size=None):
    log(sql, args)
    global __pool

    # yield from会调用一个子协程，并直接返回调用的结果
    # yield from从连接池返回一个连接
    with (yield from __pool) as coon:
        cur = yield from coon.cursor(aiomysql.DictCursor)

        # 执行SQL语句
        # SQL语句的占位符为？，MySQL的占位符为%s
        yield from cur.execute(sql.replace('?', '%s'), args or ())

        # 根据指定返回的size，返回查询结果
        if size:
            # 返回size条查询结果
            rs = cur.fetchmany(size)
        else:
            # 返回所有查询结果
            rs = cur.fetchall()
        yield from cur.close()
        logging.info('rows return: %s' % (len(rs)))
        return rs


# 封装INSERT, UPDATE, DELETE
# 语句操作参数一样，所以定义一个通用的执行函数
# 返回操作影响的行号
# @asyncio.coroutine
async def execute(sql, args, autocommit=True):
    log(sql, args)
    global __pool
    async with __pool.get() as conn:
        if not autocommit:
            conn.begin()
        try:
            # execute类型的SQL操作返回的结果只有行号，所以不需要用DictCursor
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affectedLine = cur.rowcount
                if not autocommit:
                    await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise e
        finally:
            conn.close()
        return affectedLine


# 根据输入的参数生成占位符列表
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')

    # 以','为分隔符，将列表合成字符串
    return (','.join(L))


# 定义Field类，负责保存（数据表）表的字段名和字段类型
class Field(object):
    # 表的字段包含名字、类型、是否为表的主键和默认值
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    # 当打印（数据库）表时，输出（数据库）表的信息：类名，字段类型和名字
    def __str__(self):
        return ('<%s, %s: %s>' % (self.__class__.__name__, self.column_type, self.name))


# -*-定义不同类型的衍生Field -*-
# -*-表的不同列的字段的类型不一样
class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'Text', False, default)


# -*-定义Model的元类
# 所有的元类都继承自type
# ModelMetaclass元类定义了所有Model基类(继承ModelMetaclass)的子类实现的操作

# -*-ModelMetaclass的工作主要是为了一个数据库表映射成一个封装的类做准备：
# 读取具体子类（user）的映射信息
# 创造类的时候，排除对Model类的修改
# 在当前类中查找所有类属性(attr)，如果找到Field属性，就将其保存到__mappings__中，同时从类属性中删除Field（防止实例属性屏蔽类的同名属性）
# 将数据库表名保存至__table__中

# 完成这些工作后，就可以在Model中定义各种数据库的操作方法

class ModelMetaclass(type):
    # __new__控制__init__的执行，所以在其执行之前
    # cls:代表__init__的类，此参数在实例化时由Python解释器自动提供
    # bases:代表继承父类的集合
    # attrs:类的方法集合
    def __new__(cls, name, bases, attrs):
        # 排除Model：
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)

        # 获取table名词
        tableName = attrs.get('__table__', None) or name
        logging.info('found Model: %s (table: %s)' % (name, tableName))

        # 获取Field和主键名
        mappings = dict()
        fields = []
        primarykey = None
        for k, v in attrs.items():
            # Fields属性
            if isinstance(v, Field):
                # 此处打印的k是类的一个属性，v是这个属性在数据库中对应的Field列表属性
                logging.info('  found mapping: %s --> %s' % (k, v))
                mappings[k] = v

                # 找到了主键
                if v.primary_key:
                    # 如果此时类实例已存在主键，说明主键重复了
                    if primarykey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    # 否则将此列设为列表的主键
                    primarykey = k
                else:
                    fields.append(k)
        # end for

        if not primarykey:
            raise RuntimeError('Primary key is nor founnd')

        # 从类属性中删除Field属性
        for k in mappings.keys():
            attrs.pop(k)

        # 保存除主键外的属性名为``(运算出字符串)列表形式
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))

        # 保存属性和列的映射关系
        attrs['__mappings__'] = mappings
        # 保存表名
        attrs['__table__'] = tableName
        # 保存主键属性名
        attrs['__primary_key__'] = primarykey
        # 保存除主键外的属性名
        attrs['__fields__'] = fields

        # 构造默认的SELECT, INSERT, UPDATE, DELETE语句
        attrs['__select__'] = 'select `%s` , %s from `%s`' % (primarykey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values(%s)' % (
        tableName, ', '.join(escaped_fields), primarykey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set `%s` where `%s` = ?' % (
        tableName, ', '.join(map(lambda f: '`%s` = ?' % (mappings.get(f).name or f), fields)), primarykey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primarykey)

        return type.__new__(cls, name, bases, attrs)


# 定义ORM所有映射的基类：Model
# Model类的任意子类可以映射一个数据库表
# Model类可以看作是对所有数据表操作的基本定义的映射

# 基于字典查询形式
# Model从dict继承，拥有字典的所有功能，同时实现特殊方法__getattr__和__setattr__，能够实现属性操作
# 实现数据库操作的所有方法，定义为class方法， 所有继承自Model都具有数据库操作方法

class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r' "Model" object has no attribute: %s' % (key))

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        # 内建函数getattr会自动处理
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if not value:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    # 类方法有类变量cls传入，从而可以用cls做一些相关的处理。并且有子类继承时，调用该类方法时，传入的类变量cls是子类而非父类
    @asyncio.coroutine
    def findAll(cls, where=None, args=None, **kw):
        '''find objects by where clause'''
        sql = [cls.__select__]

        if where:
            sql.append('where')
            sql.append(where)

        if args is None:
            args = []

        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)

        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                sql.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?,?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = yield from select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    #根据列名和条件查看数据库有多少条信息
    @classmethod
    @asyncio.coroutine
    def findNumber(cls, selectField, where=None, args=None):
        '''find number by select and where'''
        sql = ['select %s __num__ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = yield from select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['__num__']

    #根据主键查找一个实例的信息
    @classmethod
    @asyncio.coroutine
    def find(cls, primarykey):
        '''find object by primary key'''
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [primarykey], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    @asyncio.coroutine
    def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = yield from execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    @asyncio.coroutine
    def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    @asyncio.coroutine
    def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
