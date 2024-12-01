import pytest
from pathlib import Path
from janito.xmlchangeparser import XMLChangeParser, XMLChange, XMLBlock

@pytest.fixture
def parser():
    return XMLChangeParser()

# Remove unused sample_xml fixture

def test_parse_empty_create_block(parser):
    test_xml = '''<fileChanges>
    <change path="hello.py" operation="create">
        <block description="Create new file hello.py">
            <oldContent></oldContent>
            <newContent></newContent>
        </block>
    </change>
</fileChanges>'''

    changes = parser.parse_response(test_xml)
    assert len(changes) == 1
    
    change = changes[0]
    assert change.path.name == "hello.py"
    assert change.operation == "create"
    assert len(change.blocks) == 1
    
    block = change.blocks[0]
    assert block.description == "Create new file hello.py"
    assert block.old_content == []
    assert block.new_content == []

def test_parse_create_with_content(parser):
    test_xml = '''<fileChanges>
    <change path="test.py" operation="create">
        <block description="Create test file">
            <oldContent>
            </oldContent>
            <newContent>
def test_function():
    return True
            </newContent>
        </block>
    </change>
</fileChanges>'''

    changes = parser.parse_response(test_xml)
    assert len(changes) == 1
    
    change = changes[0]
    assert change.path.name == "test.py"
    assert change.operation == "create"
    
    block = change.blocks[0]
    assert block.old_content == []
    assert len(block.new_content) == 2
    assert "def test_function():" in block.new_content
    assert "    return True" in block.new_content

# Remove test_parse_create_hello_world as it's redundant with test_parse_create_with_content

def test_parse_modify_block(parser):
    test_xml = '''<fileChanges>
    <change path="existing.py" operation="modify">
        <block description="Update function">
            <oldContent>
def old_function():
    pass
            </oldContent>
            <newContent>
def new_function():
    return True
            </newContent>
        </block>
    </change>
</fileChanges>'''

    changes = parser.parse_response(test_xml)
    assert len(changes) == 1
    
    change = changes[0]
    assert change.path.name == "existing.py"
    assert change.operation == "modify"
    
    block = change.blocks[0]
    assert "def old_function():" in block.old_content
    assert "    pass" in block.old_content
    assert "def new_function():" in block.new_content
    assert "    return True" in block.new_content

def test_parse_multiple_blocks(parser):
    test_xml = '''<fileChanges>
    <change path="multi.py" operation="modify">
        <block description="First change">
            <oldContent>
def first(): pass
            </oldContent>
            <newContent>
def first(): return 1
            </newContent>
        </block>
        <block description="Second change">
            <oldContent>
def second(): pass
            </oldContent>
            <newContent>
def second(): return 2
            </newContent>
        </block>
    </change>
</fileChanges>'''

    changes = parser.parse_response(test_xml)
    assert len(changes) == 1
    assert len(changes[0].blocks) == 2
    
    block1, block2 = changes[0].blocks
    assert block1.description == "First change"
    assert block2.description == "Second change"

# Keep remaining validation tests

def test_parse_invalid_xml(parser):
    invalid_xml = "<invalid>xml</invalid>"
    changes = parser.parse_response(invalid_xml)
    assert len(changes) == 0

def test_parse_empty_response(parser):
    empty_response = ""
    changes = parser.parse_response(empty_response)
    assert len(changes) == 0

def test_parse_invalid_operation(parser):
    invalid_op_xml = '''<fileChanges>
    <change path="test.py" operation="invalid">
        <block description="Test">
            <oldContent></oldContent>
            <newContent>test</newContent>
        </block>
    </change>
</fileChanges>'''
    changes = parser.parse_response(invalid_op_xml)
    assert len(changes) == 0

def test_parse_missing_attributes(parser):
    missing_attr_xml = '''<fileChanges>
    <change path="test.py">
        <block>
            <oldContent></oldContent>
            <newContent>test</newContent>
        </block>
    </change>
</fileChanges>'''
    changes = parser.parse_response(missing_attr_xml)
    assert len(changes) == 0

def test_invalid_tag_format(parser):
    invalid_xml = '''<fileChanges><change path="test.py" operation="create">
        <block description="Test"><oldContent></oldContent>
        <newContent>test</newContent></block></change></fileChanges>'''
    changes = parser.parse_response(invalid_xml)
    assert len(changes) == 0

def test_valid_tag_format(parser):
    valid_xml = '''<fileChanges>
    <change path="test.py" operation="create">
        <block description="Test">
            <oldContent>
            </oldContent>
            <newContent>
                test
            </newContent>
        </block>
    </change>
</fileChanges>'''
    changes = parser.parse_response(valid_xml)
    assert len(changes) == 1
    assert changes[0].path.name == "test.py"
    assert len(changes[0].blocks) == 1