import orm
import asyncio
from models import User, Blog, Comment
import logging
logging.basicConfig(level=logging.INFO)

async def test(loop):
    await orm.create_pool(user='root', password='root', db='awesome', loop=loop)

    # u = User(name='Test', email='test@example.com', passwd='12345678', image='about:blank', admin=0)
    # yield from u.save()

    # 测试find Number语句
    rows = await User.findNumber()
    logging.info('rows is %s' % rows)

    # 测试insert语句
    if rows < 3:
        for idx in range(5):
            u = User(
                name = 'test%s' % idx,
                email = 'test%s@org.com' % idx,
                passwd = 'test%s' % idx,
                image = 'about:blank',
                admin = 0
            )
            row = await User.findAll(where='email = ?', args=[u.email])
            if len(row) == 0:
                await u.save()
            else:
                print('the email is already registered...')

    #测试select语句
    users = await User.findAll(orderBy='created_at')
    for user in users:
        logging.info('name: %s, password: %s, created_at: %s' % (user.name, user.passwd, user.created_at))

    #测试update语句
    user = users[1]
    user.email = 'guest@orm.com'
    user.name = 'guest'
    await user.update()

    #测试查找指定用户
    test_user = await User.find(user.id)
    logging.info('name: %s, email: %s' % (test_user.name, test_user.email))

    #测试delete语句
    users = await User.findAll(orderBy='created_at', limit=(0, 3))
    for user in users:
        logging.info('delete user: %s' % user.name)
        await user.remove()


    await orm.destroy_pool()  # 这里先销毁连接池
    print('test ok')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(loop))
    loop.close()
