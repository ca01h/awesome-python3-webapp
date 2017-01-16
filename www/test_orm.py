import orm
import asyncio
from models import User, Blog, Comment

def test(loop):
	yield from orm.create_pool(user='root', password='root', db='awesome', loop=loop)

	u = User(name='Test', email='test@example.com', passwd='12345678', image='about:blank', admin=0)

	yield from u.save()

	yield from orm.destroy_pool()  # 这里先销毁连接池
	print('test ok')

if __name__ == '__main__':
	loop = asyncio.get_event_loop()
	loop.run_until_complete(test(loop))
	loop.close()