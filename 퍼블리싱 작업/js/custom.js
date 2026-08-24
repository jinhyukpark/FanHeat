//검색창 효과
$(document).ready(function(){
    if (matchMedia("(max-width:600px) , (min-width:1024px) and (max-width:1312px)").matches) {
        $(".search > button").click(function () {
            $(".search, .input").toggleClass("active");
            $("input[type='search']").focus();
            if($('.keyword').css("display") == "none"){
                jQuery('.keyword').delay(600).fadeIn(1000);
            } else {
                jQuery('.keyword').hide();
            }
            if(matchMedia("(max-width:480px)").matches){
                $('.keyword.after').remove();//480이하 키워드 나타나지 않기   
            }
        });
    }
}); 

//longin_after 마이페이지 클릭 시 menu popup
$(document).ready(function () {
/*    $(".mypage").mouseover(function(){
        $(".menu_wrap").addClass("hover");
        $(".menu_wrap").mouseleave(function(){
            $(".menu_wrap").removeClass("hover");
        });
    });
    $(".mypage").mouseleave(function(){
        $(".menu_wrap").removeClass("hover");          
    });*/
    $('.menu_wrap').hide();
    $(".mypage").mouseover(function(){
        $('.menu_wrap').show();
        $(".menu_wrap").mouseleave(function(){
           $(".menu_wrap").hide(); 
        });
    });
//     $(".login_wrap > .mypage").mouseleave(function(){
//        $(".menu_wrap").css("display","none");
//    });
//    $(".login_wrap > .mypage").mouseleave(function(){
//        $(".menu_wrap").removeClass("hover");
//    });
});

 //K-pop Best Awards sotby & posting_write Modal 뮤직리스트 sortby
$(document).ready(function () {
    $(".sortby > li").click(function () {
        var me = $(this).index();
        $('.sortby > li').removeClass('on');
        $(this).addClass('on');
    });
    $(".musiclist_sortby > li").click(function () {
        var me = $(this).index();
        $('.musiclist_sortby > li').removeClass('on');
        $(this).addClass('on');
    });
});

//sub_post 댓글창 토글
$('.reply_form_wrap').hide();

$('.reply_bt').on('click', function(){
    $(this).parent().siblings('.reply_form_wrap').toggle();
    $('.reply_form').children('textarea').focus();
});

//음악검색 PopUp
$(document).ready(function () {
    $("#musicadd").click(function(){
        $("#popup").addClass("active");
    });
    $(".popup_close").click(function(){
        $("#popup").removeClass("active");
    });
});

//posting_write Modal 음악검색 선택
$(document).ready(function () {
    $('.music_list li').click(function () {
        $(this).toggleClass('select');
    })
});

//posting_write 수익분배 추가/삭제
$(document).ready(function(){
    $('.contbr_bt').on('click', function(){
        $('#contbr_add_wrap').clone(true).appendTo('.form_contributors');
    });
    $(".delet").click(function () {
        $(this).closest("#contbr_add_wrap").not('.contbr_bt + .contbr_add_wrap').remove();
    }); 
});

