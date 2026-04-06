

def test_compile(statement:str, loc_variables:dict):
    exec(statement, globals(), loc_variables)
    print("result=", loc_variables['result'])
    
if __name__ == '__main__':
    variables = {"a":1, "b": 2}
    test_compile("result=a+b", variables)


